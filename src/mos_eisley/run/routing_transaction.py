"""Offline G6 transaction simulator. No credential or live provider adapter."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import stat
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ToolDefinition
from mos_eisley.evaluation.models import RouteCandidate
from mos_eisley.evaluation.routing_protocol import ObservablePromptFeatures
from mos_eisley.run.exact_route import ExactRouteRequirements, ExactRouteSelection
from mos_eisley.run.routing_preflight import (
    RoutingRuntimePreflight,
    RoutingRuntimeSources,
    verify_routing_runtime_sources,
)
from mos_eisley.run.store import private_write
from mos_eisley.run.witnessed_admission import (
    SyntheticWitnessedAdmission,
    WitnessedAdmissionReceipt,
    WitnessedAttempt,
    verify_admission_receipt,
)

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]
_ATTEMPT_DOMAIN = b"mos-eisley/g6-offline-attempt/v1\0"
_INERT_OPTIONS_SHA256 = digest(b"mos-eisley/g6-offline-no-provider-options/v1\0")
_WRITER = object()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("offline routing time must be explicit UTC")
    return value


def _connect(path: Path) -> sqlite3.Connection:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError("offline routing store must be private and regular")
    connection = sqlite3.connect(
        path.absolute().as_uri() + "?mode=rw",
        uri=True,
        timeout=2.0,
        isolation_level=None,
    )
    try:
        connection.execute("PRAGMA synchronous=EXTRA")
        connection.execute("PRAGMA trusted_schema=OFF")
        if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            raise ValueError("offline routing store requires rollback journaling")
        return connection
    except BaseException:
        connection.close()
        raise


def _policy[T: Contract](connection: sqlite3.Connection, model: type[T]) -> T:
    rows = connection.execute("SELECT policy_json FROM policy").fetchall()
    if len(rows) != 1:
        raise ValueError("offline routing store policy is missing")
    policy = model.model_validate_json(rows[0][0])
    if canonical_bytes(policy) != rows[0][0]:
        raise ValueError("offline routing store policy is noncanonical")
    return policy


def _create_policy(path: Path, policy: Contract) -> None:
    private_write(path, b"")
    with closing(_connect(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE policy (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
            "policy_json BLOB NOT NULL) STRICT"
        )
        connection.execute(
            "INSERT INTO policy VALUES (1, ?)", (canonical_bytes(policy),)
        )


class OfflineExecutionProfile(Contract):
    """Reviewed-fixture request shape; never a live entitlement."""

    schema_version: Literal[1] = 1
    role: Identifier
    output_contract: Identifier
    requires_structured_output: bool
    tool_names: Annotated[tuple[Identifier, ...], Field(max_length=64)]
    tools_sha256: Digest
    provider_options_sha256: Digest
    max_context_bytes: Annotated[int, Field(gt=0)]
    max_output_bytes: Annotated[int, Field(gt=0)]
    max_output_tokens: Annotated[int, Field(gt=0)]
    max_input_tokens: Annotated[int, Field(gt=0)]
    input_microusd_per_token: Annotated[int, Field(ge=0)]
    output_microusd_per_token: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def canonical_tools(self) -> Self:
        if self.tool_names != tuple(sorted(set(self.tool_names))):
            raise ValueError("offline profile tools must be sorted and unique")
        return self

    @property
    def profile_sha256(self) -> str:
        return digest(canonical_bytes(self))


def offline_provider_options_sha256() -> str:
    """The only provider-option set accepted by the inert transport: none."""
    return _INERT_OPTIONS_SHA256


class OfflineRoutingEnvelope(Contract):
    schema_version: Literal[1] = 1
    owner_id: Identifier
    cohort_id: Identifier
    session_id: Identifier
    task_id: Identifier
    stage_id: Identifier
    attempt_id: Identifier
    selection_sha256: Digest
    profile_sha256: Digest
    request_sha256: Digest
    control_sequence: Annotated[int, Field(ge=0)]
    control_digest: Digest
    maximum_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]

    @property
    def attempt_key(self) -> str:
        identity = (
            self.owner_id,
            self.cohort_id,
            self.task_id,
            self.stage_id,
            self.attempt_id,
        )
        return digest(
            _ATTEMPT_DOMAIN + canonical_bytes(_AttemptIdentity(values=identity))
        )

    @property
    def envelope_sha256(self) -> str:
        return digest(canonical_bytes(self))


class _AttemptIdentity(Contract):
    values: tuple[Identifier, Identifier, Identifier, Identifier, Identifier]


class OfflineToolSet(Contract):
    tools: tuple[ToolDefinition, ...]


def offline_toolset_sha256(tools: tuple[ToolDefinition, ...]) -> str:
    return digest(canonical_bytes(OfflineToolSet(tools=tools)))


class SyntheticWitnessPolicy(Contract):
    schema_version: Literal[1] = 1
    witness_id: Digest
    initial_control_digest: Digest


class WitnessState(Contract):
    sequence: Annotated[int, Field(ge=0)]
    control_digest: Digest
    stopped: bool


class WitnessClaim(Contract):
    attempt_key: Digest
    request_sha256: Digest
    claim_id: Digest
    control_sequence: Annotated[int, Field(ge=0)]
    control_digest: Digest


class SyntheticRoutingWitness:
    """Separate SQLite fixture with atomic claim/stop order; no real attestation."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _policy(connection, SyntheticWitnessPolicy)

    @classmethod
    def create(cls, path: Path, initial_control_digest: str) -> Self:
        policy = SyntheticWitnessPolicy(
            witness_id=digest(uuid4().bytes),
            initial_control_digest=initial_control_digest,
        )
        _create_policy(path, policy)
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE control (singleton INTEGER PRIMARY KEY "
                "CHECK(singleton=1), "
                "sequence INTEGER NOT NULL, control_digest TEXT NOT NULL, "
                "stopped INTEGER NOT NULL) STRICT"
            )
            connection.execute(
                "INSERT INTO control VALUES (1, 0, ?, 0)",
                (initial_control_digest,),
            )
            connection.execute(
                "CREATE TABLE claims (attempt_key TEXT PRIMARY KEY, "
                "request_sha256 TEXT NOT NULL, claim_id TEXT NOT NULL UNIQUE, "
                "control_sequence INTEGER NOT NULL, "
                "control_digest TEXT NOT NULL) STRICT"
            )
        return cls(path)

    def _state(self, connection: sqlite3.Connection) -> WitnessState:
        if _policy(connection, SyntheticWitnessPolicy) != self.policy:
            raise ValueError("synthetic witness identity changed")
        rows = connection.execute(
            "SELECT sequence, control_digest, stopped FROM control"
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("synthetic witness control is invalid")
        return WitnessState(
            sequence=rows[0][0], control_digest=rows[0][1], stopped=bool(rows[0][2])
        )

    def read_latest(self) -> WitnessState:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            return self._state(connection)

    def stop(self, new_control_digest: str) -> WitnessState:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            state = self._state(connection)
            connection.execute(
                "UPDATE control SET sequence=?, control_digest=?, stopped=1",
                (state.sequence + 1, new_control_digest),
            )
            return self._state(connection)

    def claim(
        self, attempt_key: str, request_sha256: str, expected: WitnessState
    ) -> WitnessClaim:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            state = self._state(connection)
            if state != expected or state.stopped:
                raise ValueError("synthetic witness control changed or stopped")
            claim = WitnessClaim(
                attempt_key=attempt_key,
                request_sha256=request_sha256,
                claim_id=digest(
                    b"mos-eisley/g6-offline-claim/v1\0"
                    + bytes.fromhex(attempt_key)
                    + bytes.fromhex(request_sha256)
                ),
                control_sequence=state.sequence,
                control_digest=state.control_digest,
            )
            connection.execute(
                "INSERT INTO claims VALUES (?, ?, ?, ?, ?)",
                (
                    claim.attempt_key,
                    claim.request_sha256,
                    claim.claim_id,
                    claim.control_sequence,
                    claim.control_digest,
                ),
            )
            return claim

    def inspect_claim(self, attempt_key: str) -> WitnessClaim | None:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            self._state(connection)
            row = connection.execute(
                "SELECT attempt_key, request_sha256, claim_id, control_sequence, "
                "control_digest FROM claims WHERE attempt_key=?",
                (attempt_key,),
            ).fetchone()
            return (
                None
                if row is None
                else WitnessClaim.model_validate(
                    dict(
                        zip(
                            (
                                "attempt_key",
                                "request_sha256",
                                "claim_id",
                                "control_sequence",
                                "control_digest",
                            ),
                            row,
                            strict=True,
                        )
                    )
                )
            )


class SyntheticBudgetPolicy(Contract):
    schema_version: Literal[1] = 1
    budget_id: Digest
    owner_id: Identifier
    cohort_id: Identifier
    task_ceiling_microusd: Annotated[int, Field(gt=0)]
    session_ceiling_microusd: Annotated[int, Field(gt=0)]
    cohort_ceiling_microusd: Annotated[int, Field(gt=0)]


class BudgetEntry(Contract):
    attempt_key: Digest
    reservation_sha256: Digest
    reserved_microusd: Money
    charged_microusd: Money
    status: Literal["held", "settled", "uncertain", "violation"]


class SyntheticRoutingBudget:
    """Offline atomic scope admission; local rollback is still possible."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _policy(connection, SyntheticBudgetPolicy)

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        owner_id: str,
        cohort_id: str,
        task_ceiling_microusd: int,
        session_ceiling_microusd: int,
        cohort_ceiling_microusd: int,
    ) -> Self:
        policy = SyntheticBudgetPolicy(
            budget_id=digest(uuid4().bytes),
            owner_id=owner_id,
            cohort_id=cohort_id,
            task_ceiling_microusd=task_ceiling_microusd,
            session_ceiling_microusd=session_ceiling_microusd,
            cohort_ceiling_microusd=cohort_ceiling_microusd,
        )
        _create_policy(path, policy)
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE entries (attempt_key TEXT PRIMARY KEY, "
                "reservation_sha256 TEXT NOT NULL, task_id TEXT NOT NULL, "
                "session_id TEXT NOT NULL, reserved INTEGER NOT NULL, "
                "charged INTEGER NOT NULL, status TEXT NOT NULL) STRICT"
            )
        return cls(path)

    def _check(self, connection: sqlite3.Connection) -> None:
        if _policy(connection, SyntheticBudgetPolicy) != self.policy:
            raise ValueError("synthetic budget identity changed")

    def reserve(self, envelope: OfflineRoutingEnvelope) -> BudgetEntry:
        if (
            envelope.owner_id != self.policy.owner_id
            or envelope.cohort_id != self.policy.cohort_id
        ):
            raise ValueError("synthetic budget owner or cohort mismatch")
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._check(connection)
            if connection.execute(
                "SELECT 1 FROM entries WHERE attempt_key=?",
                (envelope.attempt_key,),
            ).fetchone():
                raise ValueError("synthetic budget attempt is already consumed")
            if connection.execute(
                "SELECT 1 FROM entries WHERE status='violation' LIMIT 1"
            ).fetchone():
                raise ValueError("synthetic budget is blocked by a violation")
            for column, value, ceiling in (
                ("task_id", envelope.task_id, self.policy.task_ceiling_microusd),
                (
                    "session_id",
                    envelope.session_id,
                    self.policy.session_ceiling_microusd,
                ),
                ("cohort", None, self.policy.cohort_ceiling_microusd),
            ):
                if column == "cohort":
                    charged = connection.execute(
                        "SELECT COALESCE(SUM(charged),0) FROM entries"
                    ).fetchone()[0]
                else:
                    charged = connection.execute(
                        "SELECT COALESCE(SUM(charged),0) FROM entries "
                        f"WHERE {column}=?",
                        (value,),
                    ).fetchone()[0]
                if charged + envelope.maximum_microusd > ceiling:
                    raise ValueError("synthetic budget scope exhausted")
            entry = BudgetEntry(
                attempt_key=envelope.attempt_key,
                reservation_sha256=envelope.envelope_sha256,
                reserved_microusd=envelope.maximum_microusd,
                charged_microusd=envelope.maximum_microusd,
                status="held",
            )
            connection.execute(
                "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.attempt_key,
                    entry.reservation_sha256,
                    envelope.task_id,
                    envelope.session_id,
                    entry.reserved_microusd,
                    entry.charged_microusd,
                    entry.status,
                ),
            )
            return entry

    def inspect(self, attempt_key: str) -> BudgetEntry | None:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            self._check(connection)
            row = connection.execute(
                "SELECT attempt_key, reservation_sha256, reserved, charged, status "
                "FROM entries WHERE attempt_key=?",
                (attempt_key,),
            ).fetchone()
            return (
                None
                if row is None
                else BudgetEntry(
                    attempt_key=row[0],
                    reservation_sha256=row[1],
                    reserved_microusd=row[2],
                    charged_microusd=row[3],
                    status=row[4],
                )
            )

    def settle(
        self,
        expected: BudgetEntry,
        status: Literal["settled", "uncertain", "violation"],
        charged_microusd: int,
    ) -> BudgetEntry:
        if charged_microusd > expected.reserved_microusd or (
            status != "settled" and charged_microusd != expected.reserved_microusd
        ):
            raise ValueError("synthetic settlement exceeds or erases exposure")
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._check(connection)
            row = connection.execute(
                "SELECT reservation_sha256, reserved, charged, status FROM entries "
                "WHERE attempt_key=?",
                (expected.attempt_key,),
            ).fetchone()
            if row != (
                expected.reservation_sha256,
                expected.reserved_microusd,
                expected.reserved_microusd,
                "held",
            ):
                raise ValueError("synthetic settlement does not match held entry")
            connection.execute(
                "UPDATE entries SET charged=?, status=? WHERE attempt_key=?",
                (charged_microusd, status, expected.attempt_key),
            )
            return BudgetEntry(
                attempt_key=expected.attempt_key,
                reservation_sha256=expected.reservation_sha256,
                reserved_microusd=expected.reserved_microusd,
                charged_microusd=charged_microusd,
                status=status,
            )


class OfflineTransactionStorePolicy(Contract):
    schema_version: Literal[1] = 1
    store_id: Digest
    owner_id: Identifier
    cohort_id: Identifier
    witness_id: Digest
    budget_id: Digest
    max_attempts: Annotated[int, Field(gt=0, le=100_000)] = 10_000
    max_wait_seconds: Annotated[int, Field(gt=0, le=60)] = 30


class OfflineSendIntent(Contract):
    schema_version: Literal[1] = 1
    attempt_key: Digest
    owner_id: Identifier
    cohort_id: Identifier
    envelope_sha256: Digest
    request_sha256: Digest
    selection_sha256: Digest
    profile_sha256: Digest
    claim_id: Digest
    budget_id: Digest
    control_sequence: Annotated[int, Field(ge=0)]
    control_digest: Digest
    recorded_at: datetime
    may_have_transferred: Literal[True] = True

    @model_validator(mode="after")
    def utc_time(self) -> Self:
        _utc(self.recorded_at)
        return self

    @property
    def intent_sha256(self) -> str:
        return digest(canonical_bytes(self))


class OfflineOutcome(Contract):
    schema_version: Literal[1] = 1
    attempt_key: Digest
    intent_sha256: Digest
    status: Literal["settled", "uncertain", "violation", "abandoned"]
    charged_microusd: Money
    response_sha256: Digest | None = None
    completed_at: datetime

    @model_validator(mode="after")
    def utc_time(self) -> Self:
        _utc(self.completed_at)
        return self


class OfflineTransactionStore:
    """Pre-created private intent store, with immutable before-send records."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _policy(connection, OfflineTransactionStorePolicy)

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        owner_id: str,
        cohort_id: str,
        witness: SyntheticRoutingWitness,
        budget: SyntheticRoutingBudget,
        max_attempts: int = 10_000,
        max_wait_seconds: int = 30,
    ) -> Self:
        if owner_id != budget.policy.owner_id or cohort_id != budget.policy.cohort_id:
            raise ValueError("offline store scope and budget differ")
        policy = OfflineTransactionStorePolicy(
            store_id=digest(uuid4().bytes),
            owner_id=owner_id,
            cohort_id=cohort_id,
            witness_id=witness.policy.witness_id,
            budget_id=budget.policy.budget_id,
            max_attempts=max_attempts,
            max_wait_seconds=max_wait_seconds,
        )
        return cls._create_with_policy(path, policy)

    @classmethod
    def create_witnessed(
        cls,
        path: Path,
        *,
        admission: SyntheticWitnessedAdmission,
        max_attempts: int = 10_000,
        max_wait_seconds: int = 30,
    ) -> Self:
        policy = OfflineTransactionStorePolicy(
            store_id=digest(uuid4().bytes),
            owner_id=admission.budget_policy.owner_id,
            cohort_id=admission.budget_policy.cohort_id,
            witness_id=admission.enrollment.witness_id,
            budget_id=admission.budget_policy.policy_sha256,
            max_attempts=max_attempts,
            max_wait_seconds=max_wait_seconds,
        )
        return cls._create_with_policy(path, policy)

    @classmethod
    def _create_with_policy(
        cls, path: Path, policy: OfflineTransactionStorePolicy
    ) -> Self:
        _create_policy(path, policy)
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE intents (attempt_key TEXT PRIMARY KEY, "
                "claim_id TEXT NOT NULL UNIQUE, intent_sha256 TEXT NOT NULL UNIQUE, "
                "intent_json BLOB NOT NULL) STRICT"
            )
            connection.execute(
                "CREATE TABLE outcomes (attempt_key TEXT PRIMARY KEY, "
                "outcome_json BLOB NOT NULL) STRICT"
            )
        return cls(path)

    def _check(self, connection: sqlite3.Connection) -> None:
        if _policy(connection, OfflineTransactionStorePolicy) != self.policy:
            raise ValueError("offline transaction store identity changed")

    def get(
        self, attempt_key: str
    ) -> tuple[OfflineSendIntent, OfflineOutcome | None] | None:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            self._check(connection)
            row = connection.execute(
                "SELECT claim_id, intent_sha256, intent_json FROM intents "
                "WHERE attempt_key=?",
                (attempt_key,),
            ).fetchone()
            if row is None:
                return None
            intent = OfflineSendIntent.model_validate_json(row[2])
            if (
                intent.attempt_key != attempt_key
                or row[0] != intent.claim_id
                or row[1] != intent.intent_sha256
                or row[2] != canonical_bytes(intent)
            ):
                raise ValueError("offline send intent is invalid")
            outcome_row = connection.execute(
                "SELECT outcome_json FROM outcomes WHERE attempt_key=?", (attempt_key,)
            ).fetchone()
            if outcome_row is None:
                return intent, None
            outcome = OfflineOutcome.model_validate_json(outcome_row[0])
            if (
                outcome_row[0] != canonical_bytes(outcome)
                or outcome.attempt_key != attempt_key
                or outcome.intent_sha256 != intent.intent_sha256
            ):
                raise ValueError("offline outcome is invalid")
            return intent, outcome

    def record_before_send(self, intent: OfflineSendIntent, *, writer: object) -> None:
        if writer is not _WRITER:
            raise ValueError("offline intent writer is unauthorized")
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._check(connection)
            if (
                connection.execute("SELECT COUNT(*) FROM intents").fetchone()[0]
                >= self.policy.max_attempts
            ):
                raise ValueError("offline transaction store is full")
            if (
                intent.owner_id != self.policy.owner_id
                or intent.cohort_id != self.policy.cohort_id
                or intent.budget_id != self.policy.budget_id
            ):
                raise ValueError("offline intent scope mismatch")
            connection.execute(
                "INSERT INTO intents VALUES (?, ?, ?, ?)",
                (
                    intent.attempt_key,
                    intent.claim_id,
                    intent.intent_sha256,
                    canonical_bytes(intent),
                ),
            )

    def finish(self, outcome: OfflineOutcome, *, writer: object) -> None:
        if writer is not _WRITER:
            raise ValueError("offline outcome writer is unauthorized")
        current = self.get(outcome.attempt_key)
        if (
            current is None
            or current[0].intent_sha256 != outcome.intent_sha256
            or current[1] is not None
        ):
            raise ValueError("offline outcome has no unfinished intent")
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self._check(connection)
            connection.execute(
                "INSERT INTO outcomes VALUES (?, ?)",
                (outcome.attempt_key, canonical_bytes(outcome)),
            )


class InertRoutingResponse(Contract):
    provider: Identifier
    model: Identifier
    service_tier: Identifier
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    charged_microusd: Money


class InertRoutingTransport:
    """Records local entries only. It has no network or credential path."""

    automatic_retries: Literal[0] = 0

    def __init__(
        self,
        *,
        provider: str,
        backend: str,
        client_version: str,
        response: InertRoutingResponse | None = None,
        error: BaseException | None = None,
        entry_log_path: Path | None = None,
        exit_at_entry: bool = False,
    ):
        self.provider = provider
        self.backend = backend
        self.client_version = client_version
        self.response = response
        self.error = error
        self.entry_log_path = entry_log_path
        self.exit_at_entry = exit_at_entry
        self.entries: list[str] = []

    async def send(self, request: ModelRequest) -> InertRoutingResponse:
        self.entries.append(digest(canonical_bytes(request)))
        if self.entry_log_path is not None:
            with self.entry_log_path.open("a") as stream:
                stream.write("entered\n")
        if self.exit_at_entry:
            os._exit(77)
        await asyncio.sleep(0)
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise ValueError("inert response unavailable")
        return self.response


class SyntheticRoutingMonitor:
    """A fail-closed offline health fixture; no operational alerting claim."""

    def __init__(self) -> None:
        self.healthy = True

    def check(self) -> None:
        if not self.healthy:
            raise ValueError("synthetic routing monitor unavailable")


class SyntheticRouteObservation(Contract):
    """One inert exact-route availability observation, without live authority."""

    route: RouteCandidate
    observed_at: datetime
    valid_until: datetime
    available: bool

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        _utc(self.observed_at)
        _utc(self.valid_until)
        if self.valid_until <= self.observed_at:
            raise ValueError("synthetic route observation window is invalid")
        return self


class SyntheticExactRouteProbe:
    """Mutable fixture read before claim and before inert transport entry."""

    def __init__(self, current: SyntheticRouteObservation):
        self.current = current
        self.reads = 0

    def check(self, selection: ExactRouteSelection, now: datetime) -> None:
        self.reads += 1
        current = self.current
        if (
            current.route != selection.route
            or not current.available
            or not current.observed_at <= now < current.valid_until
        ):
            raise ValueError("synthetic exact route is unavailable or stale")


class OfflineRoutingStatus(Contract):
    attempt_key: Digest
    phase: Literal["absent", "reserved", "claimed", "intent", "finished"]
    budget_status: Literal["absent", "held", "settled", "uncertain", "violation"]
    witness_claimed: bool
    intent_committed: bool
    outcome: Literal["settled", "uncertain", "violation", "abandoned"] | None
    may_have_transferred: bool
    retry_permitted: Literal[False] = False


def inspect_offline_routing_transaction(
    envelope: OfflineRoutingEnvelope,
    witness: SyntheticRoutingWitness,
    budget: SyntheticRoutingBudget,
    store: OfflineTransactionStore,
) -> OfflineRoutingStatus:
    """Correlate durable facts without admission, mutation, send or refund."""
    _check_store_links(envelope, witness, budget, store)
    entry = budget.inspect(envelope.attempt_key)
    claim = witness.inspect_claim(envelope.attempt_key)
    record = store.get(envelope.attempt_key)
    if entry is not None and entry.reservation_sha256 != envelope.envelope_sha256:
        raise ValueError("offline budget reservation conflicts with envelope")
    if claim is not None and (
        claim.request_sha256 != envelope.request_sha256
        or claim.control_sequence != envelope.control_sequence
        or claim.control_digest != envelope.control_digest
    ):
        raise ValueError("offline witness claim conflicts with envelope")
    if record is not None:
        intent, outcome = record
        if (
            entry is None
            or claim is None
            or intent.envelope_sha256 != envelope.envelope_sha256
            or intent.request_sha256 != envelope.request_sha256
            or intent.selection_sha256 != envelope.selection_sha256
            or intent.profile_sha256 != envelope.profile_sha256
            or intent.claim_id != claim.claim_id
        ):
            raise ValueError("offline intent provenance disagrees with stores")
    else:
        outcome = None
    if claim is not None and entry is None:
        raise ValueError("offline claim has no budget reservation")
    if outcome is not None and entry is not None:
        expected_status = "held" if outcome.status == "abandoned" else outcome.status
        if (
            entry.status != expected_status
            or entry.charged_microusd != outcome.charged_microusd
        ):
            raise ValueError("offline outcome and budget disagree")
    return OfflineRoutingStatus(
        attempt_key=envelope.attempt_key,
        phase=(
            "finished"
            if outcome is not None
            else "intent"
            if record is not None
            else "claimed"
            if claim is not None
            else "reserved"
            if entry is not None
            else "absent"
        ),
        budget_status="absent" if entry is None else entry.status,
        witness_claimed=claim is not None,
        intent_committed=record is not None,
        outcome=None if outcome is None else outcome.status,
        may_have_transferred=record is not None,
    )


def _check_store_links(
    envelope: OfflineRoutingEnvelope,
    witness: SyntheticRoutingWitness,
    budget: SyntheticRoutingBudget,
    store: OfflineTransactionStore,
) -> None:
    if (
        store.policy.owner_id != envelope.owner_id
        or store.policy.cohort_id != envelope.cohort_id
        or budget.policy.owner_id != envelope.owner_id
        or budget.policy.cohort_id != envelope.cohort_id
        or store.policy.witness_id != witness.policy.witness_id
        or store.policy.budget_id != budget.policy.budget_id
    ):
        raise ValueError("offline routing store provenance mismatch")


def _validate_request(
    envelope: OfflineRoutingEnvelope,
    selection: ExactRouteSelection,
    preflight: RoutingRuntimePreflight,
    requirements: ExactRouteRequirements,
    profile: OfflineExecutionProfile,
    request: ModelRequest,
    transport: InertRoutingTransport,
    now: datetime,
) -> None:
    preflight.check_current(now)
    route = selection.route
    if (
        envelope.selection_sha256 != digest(canonical_bytes(selection))
        or envelope.profile_sha256 != profile.profile_sha256
        or envelope.request_sha256 != digest(canonical_bytes(request))
        or selection.preflight_sha256 != preflight.preflight_sha256
        or selection.candidate_policy_sha256 != preflight.candidate_policy_sha256
        or selection.requirements_sha256 != requirements.requirements_sha256
        or selection.candidate_id not in preflight.eligible_candidate_ids
        or selection.registry_verification != "fixture"
        or selection.role != profile.role
        or requirements.role != profile.role
        or requirements.output_contract != profile.output_contract
        or requirements.requires_structured_output != profile.requires_structured_output
        or requirements.tool_requirements != profile.tool_names
        or tuple(sorted(tool.name for tool in request.tools)) != profile.tool_names
        or offline_toolset_sha256(request.tools) != profile.tools_sha256
        or profile.provider_options_sha256 != _INERT_OPTIONS_SHA256
        or len(canonical_bytes(request)) > profile.max_context_bytes
        or request.provider != route.provider
        or request.model != route.model
        or request.effort != route.effort
        or request.system != route.prompt.instructions
        or request.max_output != profile.max_output_bytes
        or request.max_output_tokens != profile.max_output_tokens
        or envelope.maximum_microusd
        != (
            profile.max_input_tokens * profile.input_microusd_per_token
            + profile.max_output_tokens * profile.output_microusd_per_token
        )
        or transport.provider != route.provider
        or transport.backend != route.backend
        or transport.client_version != route.client_version
        or transport.automatic_retries != 0
    ):
        raise ValueError("offline routing exact request mismatch")


def _finish(
    envelope: OfflineRoutingEnvelope,
    intent: OfflineSendIntent,
    budget: SyntheticRoutingBudget,
    store: OfflineTransactionStore,
    entry: BudgetEntry,
    status: Literal["settled", "uncertain", "violation"],
    charged: int,
    now: datetime,
    response_sha256: str | None = None,
) -> OfflineOutcome:
    budget.settle(entry, status, charged)
    outcome = OfflineOutcome(
        attempt_key=envelope.attempt_key,
        intent_sha256=intent.intent_sha256,
        status=status,
        charged_microusd=charged,
        response_sha256=response_sha256,
        completed_at=now,
    )
    store.finish(outcome, writer=_WRITER)
    return outcome


async def execute_offline_routing_transaction(
    *,
    envelope: OfflineRoutingEnvelope,
    selection: ExactRouteSelection,
    preflight: RoutingRuntimePreflight,
    requirements: ExactRouteRequirements,
    profile: OfflineExecutionProfile,
    request: ModelRequest,
    witness: SyntheticRoutingWitness,
    budget: SyntheticRoutingBudget,
    store: OfflineTransactionStore,
    transport: InertRoutingTransport,
    monitor: SyntheticRoutingMonitor,
    now: datetime,
    fault: Callable[[str], None] | None = None,
) -> OfflineOutcome:
    """Spend, claim, fsync intent, check stop, enter inert transport once."""
    _utc(now)
    _check_store_links(envelope, witness, budget, store)
    if (
        type(transport) is not InertRoutingTransport
        or type(monitor) is not SyntheticRoutingMonitor
    ):
        raise ValueError("offline routing requires exact inert fixtures")
    _validate_request(
        envelope, selection, preflight, requirements, profile, request, transport, now
    )
    expected = WitnessState(
        sequence=envelope.control_sequence,
        control_digest=envelope.control_digest,
        stopped=False,
    )
    if witness.read_latest() != expected:
        raise ValueError("offline witness control mismatch")
    monitor.check()

    def cut(name: str) -> None:
        if fault is not None:
            fault(name)

    cut("before_reserve")
    entry = budget.reserve(envelope)
    cut("after_reserve")
    claim = witness.claim(envelope.attempt_key, envelope.request_sha256, expected)
    cut("after_claim")
    intent = OfflineSendIntent(
        attempt_key=envelope.attempt_key,
        owner_id=envelope.owner_id,
        cohort_id=envelope.cohort_id,
        envelope_sha256=envelope.envelope_sha256,
        request_sha256=envelope.request_sha256,
        selection_sha256=envelope.selection_sha256,
        profile_sha256=envelope.profile_sha256,
        claim_id=claim.claim_id,
        budget_id=budget.policy.budget_id,
        control_sequence=claim.control_sequence,
        control_digest=claim.control_digest,
        recorded_at=now,
    )
    store.record_before_send(intent, writer=_WRITER)
    cut("after_intent")
    current = witness.read_latest()
    try:
        monitor.check()
        ready = current == expected
    except ValueError:
        ready = False
    if not ready:
        outcome = OfflineOutcome(
            attempt_key=envelope.attempt_key,
            intent_sha256=intent.intent_sha256,
            status="abandoned",
            charged_microusd=entry.reserved_microusd,
            completed_at=now,
        )
        store.finish(outcome, writer=_WRITER)
        return outcome
    cut("after_final_check")
    try:
        async with asyncio.timeout(store.policy.max_wait_seconds):
            response = InertRoutingResponse.model_validate(
                await transport.send(request)
            )
    except asyncio.CancelledError:
        _finish(
            envelope,
            intent,
            budget,
            store,
            entry,
            "uncertain",
            entry.reserved_microusd,
            now,
        )
        raise
    except Exception:
        return _finish(
            envelope,
            intent,
            budget,
            store,
            entry,
            "uncertain",
            entry.reserved_microusd,
            now,
        )
    response_sha256 = digest(canonical_bytes(response))
    if (
        response.provider != request.provider
        or response.model != request.model
        or response.service_tier != "default"
        or response.input_tokens > profile.max_input_tokens
        or response.output_tokens > profile.max_output_tokens
        or response.charged_microusd
        != (
            response.input_tokens * profile.input_microusd_per_token
            + response.output_tokens * profile.output_microusd_per_token
        )
        or response.charged_microusd > entry.reserved_microusd
    ):
        return _finish(
            envelope,
            intent,
            budget,
            store,
            entry,
            "violation",
            entry.reserved_microusd,
            now,
            response_sha256,
        )
    return _finish(
        envelope,
        intent,
        budget,
        store,
        entry,
        "settled",
        response.charged_microusd,
        now,
        response_sha256,
    )


def inspect_offline_witnessed_transaction(
    envelope: OfflineRoutingEnvelope,
    admission: SyntheticWitnessedAdmission,
    store: OfflineTransactionStore,
) -> OfflineRoutingStatus:
    """Read the checkpointed attempt and local intent without recovery effects."""
    _check_witnessed_store_links(envelope, admission, store)
    row = admission.inspect_attempt(
        owner_id=envelope.owner_id,
        cohort_id=envelope.cohort_id,
        attempt_key=envelope.attempt_key,
    )
    record = store.get(envelope.attempt_key)
    if row is not None and (
        row.attempt.envelope_sha256 != envelope.envelope_sha256
        or row.attempt.request_sha256 != envelope.request_sha256
    ):
        raise ValueError("witnessed attempt conflicts with offline envelope")
    if record is not None:
        intent, outcome = record
        if (
            row is None
            or intent.claim_id != row.claim_id
            or intent.envelope_sha256 != envelope.envelope_sha256
            or intent.budget_id != admission.budget_policy.policy_sha256
        ):
            raise ValueError("witnessed intent provenance is inconsistent")
        if outcome is not None and (
            row.status != ("held" if outcome.status == "abandoned" else outcome.status)
            or row.charged_microusd != outcome.charged_microusd
        ):
            raise ValueError("witnessed outcome and budget disagree")
    else:
        outcome = None
    return OfflineRoutingStatus(
        attempt_key=envelope.attempt_key,
        phase=(
            "finished"
            if outcome is not None
            else "intent"
            if record is not None
            else "claimed"
            if row is not None
            else "absent"
        ),
        budget_status="absent" if row is None else row.status,
        witness_claimed=row is not None,
        intent_committed=record is not None,
        outcome=None if outcome is None else outcome.status,
        may_have_transferred=record is not None,
    )


def _check_witnessed_store_links(
    envelope: OfflineRoutingEnvelope,
    admission: SyntheticWitnessedAdmission,
    store: OfflineTransactionStore,
) -> None:
    if (
        store.policy.owner_id != envelope.owner_id
        or store.policy.cohort_id != envelope.cohort_id
        or admission.budget_policy.owner_id != envelope.owner_id
        or admission.budget_policy.cohort_id != envelope.cohort_id
        or store.policy.witness_id != admission.enrollment.witness_id
        or store.policy.budget_id != admission.budget_policy.policy_sha256
    ):
        raise ValueError("offline witnessed transaction store provenance mismatch")


def _finish_witnessed(
    *,
    envelope: OfflineRoutingEnvelope,
    intent: OfflineSendIntent,
    admission: SyntheticWitnessedAdmission,
    store: OfflineTransactionStore,
    receipt: WitnessedAdmissionReceipt,
    status: Literal["settled", "uncertain", "violation"],
    charged_microusd: int,
    now: datetime,
    response_sha256: str | None = None,
) -> OfflineOutcome:
    admission.settle_exact(
        receipt=receipt, charged_microusd=charged_microusd, status=status, now=now
    )
    outcome = OfflineOutcome(
        attempt_key=envelope.attempt_key,
        intent_sha256=intent.intent_sha256,
        status=status,
        charged_microusd=charged_microusd,
        response_sha256=response_sha256,
        completed_at=now,
    )
    store.finish(outcome, writer=_WRITER)
    return outcome


async def execute_offline_witnessed_routing_transaction(
    *,
    envelope: OfflineRoutingEnvelope,
    selection: ExactRouteSelection,
    preflight: RoutingRuntimePreflight,
    requirements: ExactRouteRequirements,
    profile: OfflineExecutionProfile,
    request: ModelRequest,
    features: ObservablePromptFeatures,
    sources: RoutingRuntimeSources,
    admission: SyntheticWitnessedAdmission,
    store: OfflineTransactionStore,
    transport: InertRoutingTransport,
    monitor: SyntheticRoutingMonitor,
    now: datetime,
    route_probe: SyntheticExactRouteProbe | None = None,
    fault: Callable[[str], None] | None = None,
) -> OfflineOutcome:
    """Use one checkpointed control/budget claim before an inert one-use send."""
    _utc(now)
    _check_witnessed_store_links(envelope, admission, store)
    if (
        type(transport) is not InertRoutingTransport
        or type(monitor) is not SyntheticRoutingMonitor
    ):
        raise ValueError("offline witnessed routing requires inert fixtures")
    _validate_request(
        envelope, selection, preflight, requirements, profile, request, transport, now
    )
    verify_routing_runtime_sources(sources, preflight, now)
    decisions = [
        item
        for item in sources.candidate_policy.decisions
        if item.profile_id == selection.profile_id
    ]
    if (
        sources.sealed_study.protocol.feature_partition.profile(features).profile_id
        != selection.profile_id
        or features.role != requirements.role
        or features.output_contract != requirements.output_contract
        or features.tool_requirements != requirements.tool_requirements
        or sources.candidate_policy.candidate_policy_sha256
        != selection.candidate_policy_sha256
        or sources.plan.plan_sha256 != sources.candidate_policy.plan_sha256
        or len(decisions) != 1
        or decisions[0].role != selection.role
        or decisions[0].action != "calibrated_route"
        or decisions[0].selected_route != selection.route
        or decisions[0].selected_candidate_id != selection.candidate_id
        or selection.source != "calibrated_route"
        or not any(route == selection.route for route in sources.plan.routes)
        or profile.profile_sha256 != admission.budget_policy.execution_profile_sha256
    ):
        raise ValueError("offline witnessed route is not source-bound")
    local = sources.control_anchor.snapshot(sources.activation_authorities).latest
    witnessed = admission.read_current()
    if (
        local is None
        or local != witnessed.control
        or local.signed_control != sources.signed_control
        or local.anchor_entry_sha256 != preflight.anchored_control_entry_sha256
        or envelope.control_digest != local.anchor_entry_sha256
        or envelope.control_sequence != local.signed_control.control.sequence
    ):
        raise ValueError("offline witnessed latest control mismatch")
    if (
        witnessed.cohort is not None
        and type(route_probe) is not SyntheticExactRouteProbe
    ):
        raise ValueError("offline cohort requires an exact-route observation probe")
    if route_probe is not None:
        route_probe.check(selection, now)
    monitor.check()
    attempt = WitnessedAttempt(
        attempt_key=envelope.attempt_key,
        owner_id=envelope.owner_id,
        cohort_id=envelope.cohort_id,
        task_id=envelope.task_id,
        session_id=envelope.session_id,
        stage_id=envelope.stage_id,
        attempt_id=envelope.attempt_id,
        envelope_sha256=envelope.envelope_sha256,
        request_sha256=envelope.request_sha256,
        selection_sha256=envelope.selection_sha256,
        profile_sha256=envelope.profile_sha256,
        candidate_id=selection.candidate_id,
        candidate_policy_sha256=selection.candidate_policy_sha256,
        promotion_receipt_sha256=preflight.promotion_receipt_sha256,
        preflight_sha256=preflight.preflight_sha256,
        control_sequence=envelope.control_sequence,
        control_anchor_entry_sha256=envelope.control_digest,
        maximum_microusd=envelope.maximum_microusd,
        budget_policy_sha256=admission.budget_policy.policy_sha256,
    )

    def cut(name: str) -> None:
        if fault is not None:
            fault(name)

    cut("before_admission")
    if route_probe is not None:
        route_probe.check(selection, now)
    receipt = admission.claim_with_budget(
        attempt=attempt,
        expected_control=local,
        current_preflight=preflight,
        now=now,
        fault=fault,
    )
    verify_admission_receipt(receipt, admission.enrollment, attempt, now)
    claimed = admission.inspect_attempt(
        owner_id=envelope.owner_id,
        cohort_id=envelope.cohort_id,
        attempt_key=envelope.attempt_key,
    )
    if (
        claimed is None
        or claimed.claim_id != receipt.claim_id
        or claimed.admitted_generation != receipt.generation
        or claimed.status != "held"
    ):
        raise ValueError("offline witnessed receipt has no current claim")
    cut("after_admission")
    intent = OfflineSendIntent(
        attempt_key=envelope.attempt_key,
        owner_id=envelope.owner_id,
        cohort_id=envelope.cohort_id,
        envelope_sha256=envelope.envelope_sha256,
        request_sha256=envelope.request_sha256,
        selection_sha256=envelope.selection_sha256,
        profile_sha256=envelope.profile_sha256,
        claim_id=receipt.claim_id,
        budget_id=admission.budget_policy.policy_sha256,
        control_sequence=envelope.control_sequence,
        control_digest=envelope.control_digest,
        recorded_at=now,
    )
    store.record_before_send(intent, writer=_WRITER)
    cut("after_intent")
    try:
        current = admission.read_current()
        local_now = sources.control_anchor.snapshot(
            sources.activation_authorities
        ).latest
        monitor.check()
        if route_probe is not None:
            route_probe.check(selection, now)
        ready = (
            current.control == local
            and local_now == local
            and not current.control.signed_control.control.emergency_stop
        )
        if current.cohort is not None:
            release = current.cohort.signed_release.release
            ready = ready and (
                release.phase == "bounded_live"
                and release.issued_at <= now < release.valid_until
                and current.cohort.manifest.valid_from
                <= now
                < current.cohort.manifest.valid_until
                and any(
                    item.task_id == envelope.task_id
                    and item.session_id == envelope.session_id
                    and item.release_sha256 == release.release_sha256
                    for item in current.cohort.assignments
                )
            )
    except Exception:
        ready = False
    if not ready:
        outcome = OfflineOutcome(
            attempt_key=envelope.attempt_key,
            intent_sha256=intent.intent_sha256,
            status="abandoned",
            charged_microusd=envelope.maximum_microusd,
            completed_at=now,
        )
        store.finish(outcome, writer=_WRITER)
        return outcome
    cut("after_final_check")
    try:
        async with asyncio.timeout(store.policy.max_wait_seconds):
            response = InertRoutingResponse.model_validate(
                await transport.send(request)
            )
    except asyncio.CancelledError:
        _finish_witnessed(
            envelope=envelope,
            intent=intent,
            admission=admission,
            store=store,
            receipt=receipt,
            status="uncertain",
            charged_microusd=envelope.maximum_microusd,
            now=now,
        )
        raise
    except Exception:
        return _finish_witnessed(
            envelope=envelope,
            intent=intent,
            admission=admission,
            store=store,
            receipt=receipt,
            status="uncertain",
            charged_microusd=envelope.maximum_microusd,
            now=now,
        )
    response_sha256 = digest(canonical_bytes(response))
    if (
        response.provider != request.provider
        or response.model != request.model
        or response.service_tier != "default"
        or response.input_tokens > profile.max_input_tokens
        or response.output_tokens > profile.max_output_tokens
        or response.charged_microusd
        != (
            response.input_tokens * profile.input_microusd_per_token
            + response.output_tokens * profile.output_microusd_per_token
        )
        or response.charged_microusd > envelope.maximum_microusd
    ):
        return _finish_witnessed(
            envelope=envelope,
            intent=intent,
            admission=admission,
            store=store,
            receipt=receipt,
            status="violation",
            charged_microusd=envelope.maximum_microusd,
            now=now,
            response_sha256=response_sha256,
        )
    return _finish_witnessed(
        envelope=envelope,
        intent=intent,
        admission=admission,
        store=store,
        receipt=receipt,
        status="settled",
        charged_microusd=response.charged_microusd,
        now=now,
        response_sha256=response_sha256,
    )
