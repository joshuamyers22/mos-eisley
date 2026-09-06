"""Explicit local spending scopes with serialized, crash-conservative admission."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field

from mos_eisley.core.models import Contract, Digest, digest
from mos_eisley.run.store import private_write

Amount = Annotated[int, Field(ge=0, le=1_000_000_000_000)]
Outcome = Literal["settled", "uncertain", "violation"]


class LedgerPolicy(Contract):
    schema_version: Literal[1] = 1
    ledger_id: Digest
    ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]


class LedgerSnapshot(Contract):
    policy: LedgerPolicy
    charged_microusd: Amount
    available_microusd: Amount
    entries: Annotated[int, Field(ge=0)]
    unresolved_entries: Annotated[int, Field(ge=0)]
    blocked: bool


class LedgerEntry(Contract):
    entry_id: Digest
    reservation_sha256: Digest
    reserved_microusd: Amount


class LedgerSettlement(Contract):
    entry_id: Digest
    reservation_sha256: Digest
    status: Outcome
    charged_microusd: Amount


class LedgerEntryStatus(Contract):
    entry_id: Digest
    reservation_sha256: Digest
    reserved_microusd: Amount
    charged_microusd: Amount
    status: Literal["held", "settled", "uncertain", "violation"]


def _connect(path: Path) -> sqlite3.Connection:
    # mode=rw is deliberate: missing ledgers must never silently reset a budget.
    connection = sqlite3.connect(
        path.absolute().as_uri() + "?mode=rw",
        uri=True,
        timeout=0.25,
        isolation_level=None,
    )
    try:
        connection.execute("PRAGMA synchronous=EXTRA")
        if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            raise ValueError("spending ledger requires rollback journaling")
        return connection
    except BaseException:
        connection.close()
        raise


def _policy(connection: sqlite3.Connection) -> LedgerPolicy:
    rows = connection.execute(
        "SELECT version, ledger_id, ceiling FROM ledger_policy"
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("spending ledger policy is invalid")
    version, ledger_id, ceiling = rows[0]
    return LedgerPolicy(
        schema_version=version, ledger_id=ledger_id, ceiling_microusd=ceiling
    )


class SpendLedger:
    """Trusted local DB only; no provider credentials, prompt text, reset or top-up."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _policy(connection)

    @classmethod
    def create(cls, path: Path, ceiling_microusd: int) -> SpendLedger:
        policy = LedgerPolicy(
            ledger_id=digest(uuid4().bytes), ceiling_microusd=ceiling_microusd
        )
        # Parent must already exist and be trusted. Never replace an existing DB.
        private_write(path, b"")
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE ledger_policy ("
                "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
                "version INTEGER NOT NULL CHECK(version = 1), "
                "ledger_id TEXT NOT NULL, ceiling INTEGER NOT NULL "
                "CHECK(ceiling > 0 AND ceiling <= 1000000000000)) STRICT"
            )
            connection.execute(
                "INSERT INTO ledger_policy VALUES (1, 1, ?, ?)",
                (policy.ledger_id, policy.ceiling_microusd),
            )
            connection.execute(
                "CREATE TABLE entries (entry_id TEXT PRIMARY KEY, "
                "reservation_sha256 TEXT NOT NULL, reserved INTEGER NOT NULL "
                "CHECK(reserved >= 0 AND reserved <= 1000000000000), "
                "charged INTEGER NOT NULL CHECK(charged >= 0 AND charged <= reserved), "
                "status TEXT NOT NULL CHECK(status IN "
                "('held', 'settled', 'uncertain', 'violation')), "
                "CHECK(status = 'settled' OR charged = reserved)) STRICT"
            )
        return cls(path)

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection, None, None]:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if _policy(connection) != self.policy:
                raise ValueError("spending ledger identity or ceiling changed")
            yield connection

    def _snapshot(self, connection: sqlite3.Connection) -> LedgerSnapshot:
        charged, count, unresolved, violations = connection.execute(
            "SELECT COALESCE(SUM(charged), 0), COUNT(*), "
            "COALESCE(SUM(status != 'settled'), 0), "
            "COALESCE(SUM(status = 'violation'), 0) FROM entries"
        ).fetchone()
        return LedgerSnapshot(
            policy=self.policy,
            charged_microusd=charged,
            available_microusd=self.policy.ceiling_microusd - charged,
            entries=count,
            unresolved_entries=unresolved,
            blocked=violations > 0,
        )

    def snapshot(self) -> LedgerSnapshot:
        with self._transaction() as connection:
            return self._snapshot(connection)

    def entry_status(self, entry_id: str) -> LedgerEntryStatus | None:
        """Read one immutable-identity entry without creating or changing state."""
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT reservation_sha256, reserved, charged, status "
                "FROM entries WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()
            if row is None:
                return None
            return LedgerEntryStatus(
                entry_id=entry_id,
                reservation_sha256=row[0],
                reserved_microusd=row[1],
                charged_microusd=row[2],
                status=row[3],
            )

    @contextmanager
    def guard_held(
        self, expected: LedgerEntry
    ) -> Generator[LedgerEntryStatus, None, None]:
        """Hold a verified reservation read lock across a caller's local commit."""

        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _policy(connection) != self.policy:
                raise ValueError("spending ledger identity or ceiling changed")
            row = connection.execute(
                "SELECT reservation_sha256, reserved, charged, status "
                "FROM entries WHERE entry_id = ?",
                (expected.entry_id,),
            ).fetchone()
            if row is None:
                raise ValueError("spending reservation is absent")
            status = LedgerEntryStatus(
                entry_id=expected.entry_id,
                reservation_sha256=row[0],
                reserved_microusd=row[1],
                charged_microusd=row[2],
                status=row[3],
            )
            if (
                status.reservation_sha256 != expected.reservation_sha256
                or status.reserved_microusd != expected.reserved_microusd
                or status.charged_microusd != expected.reserved_microusd
                or status.status != "held"
            ):
                raise ValueError("spending reservation is not the exact held entry")
            yield status

    def reserve(self, entry: LedgerEntry) -> None:
        with self._transaction() as connection:
            snapshot = self._snapshot(connection)
            if snapshot.blocked:
                raise ValueError("spending ledger is blocked by a pricing violation")
            if entry.reserved_microusd > snapshot.available_microusd:
                raise ValueError("aggregate spending limit exceeded")
            # Duplicate entry IDs are errors, never authorization to send again.
            connection.execute(
                "INSERT INTO entries VALUES (?, ?, ?, ?, 'held')",
                (
                    entry.entry_id,
                    entry.reservation_sha256,
                    entry.reserved_microusd,
                    entry.reserved_microusd,
                ),
            )

    def settle(self, settlement: LedgerSettlement) -> None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT reservation_sha256, reserved, status FROM entries "
                "WHERE entry_id = ?",
                (settlement.entry_id,),
            ).fetchone()
            if (
                row is None
                or row[0] != settlement.reservation_sha256
                or row[2] != "held"
            ):
                raise ValueError("settlement does not match a held reservation")
            if settlement.charged_microusd > row[1] or (
                settlement.status != "settled" and settlement.charged_microusd != row[1]
            ):
                raise ValueError("settlement cannot exceed or erase reserved exposure")
            connection.execute(
                "UPDATE entries SET charged = ?, status = ? WHERE entry_id = ?",
                (settlement.charged_microusd, settlement.status, settlement.entry_id),
            )
