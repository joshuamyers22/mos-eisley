"""Append-only local anchor for signed routing activation control state."""

from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import Generator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.routing_activation import (
    RoutingActivationAuthorityPolicy,
    SignedRoutingActivationControl,
    verify_signed_routing_activation_control,
)
from mos_eisley.run.store import private_write

UtcTimestamp = Annotated[datetime, Field()]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class RoutingControlAnchorPolicy(Contract):
    schema_version: Literal[1] = 1
    anchor_id: Digest
    activation_authority_policy_sha256: Digest
    control_authority_ids: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=20)
    ]

    @model_validator(mode="after")
    def canonical_authorities(self) -> Self:
        if tuple(sorted(set(self.control_authority_ids))) != self.control_authority_ids:
            raise ValueError("control authority identities must be unique and sorted")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AnchoredRoutingControl(Contract):
    schema_version: Literal[1] = 1
    anchor_id: Digest
    previous_entry_sha256: Digest | None
    anchored_at: UtcTimestamp
    signed_control: SignedRoutingActivationControl

    @field_validator("anchored_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @property
    def anchor_entry_sha256(self) -> str:
        return digest(canonical_bytes(self))


class RoutingControlAnchorSnapshot(Contract):
    schema_version: Literal[1] = 1
    policy: RoutingControlAnchorPolicy
    entries: Annotated[int, Field(ge=0)]
    latest: AnchoredRoutingControl | None

    @model_validator(mode="after")
    def consistent_count(self) -> Self:
        if (self.entries == 0) != (self.latest is None):
            raise ValueError("anchor count and latest entry are inconsistent")
        return self

    @property
    def snapshot_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _validate_private_database(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("routing control anchor must be a regular file")
    if metadata.st_uid != os.getuid():
        raise ValueError("routing control anchor must be owned by the current user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("routing control anchor must not grant group or other access")


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
            raise ValueError("routing control anchor requires rollback journaling")
        return connection
    except BaseException:
        connection.close()
        raise


def _load_policy(connection: sqlite3.Connection) -> RoutingControlAnchorPolicy:
    rows = connection.execute(
        "SELECT version, anchor_id, authority_policy_sha256, control_authority_ids "
        "FROM anchor_policy"
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("routing control anchor policy is invalid")
    version, anchor_id, authority_digest, identities_json = rows[0]
    return RoutingControlAnchorPolicy.model_validate(
        {
            "schema_version": version,
            "anchor_id": anchor_id,
            "activation_authority_policy_sha256": authority_digest,
            "control_authority_ids": tuple(
                item for item in identities_json.split("\n") if item
            ),
        }
    )


class RoutingControlAnchor:
    """Trusted local monotonic state; contains no provider or signing credential."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _load_policy(connection)

    @classmethod
    def create(
        cls,
        path: Path,
        policy: RoutingControlAnchorPolicy,
        activation_authorities: RoutingActivationAuthorityPolicy,
    ) -> RoutingControlAnchor:
        known = {item.authority_id for item in activation_authorities.authorities}
        if (
            policy.activation_authority_policy_sha256
            != activation_authorities.policy_sha256
        ):
            raise ValueError("anchor policy does not match activation trust policy")
        if not set(policy.control_authority_ids) <= known:
            raise ValueError("control authority is absent from activation trust policy")
        private_write(path, b"")
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE anchor_policy ("
                "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
                "version INTEGER NOT NULL CHECK(version = 1), "
                "anchor_id TEXT NOT NULL, authority_policy_sha256 TEXT NOT NULL, "
                "control_authority_ids TEXT NOT NULL) STRICT"
            )
            connection.execute(
                "INSERT INTO anchor_policy VALUES (1, 1, ?, ?, ?)",
                (
                    policy.anchor_id,
                    policy.activation_authority_policy_sha256,
                    "\n".join(policy.control_authority_ids),
                ),
            )
            connection.execute(
                "CREATE TABLE control_entries ("
                "sequence INTEGER PRIMARY KEY CHECK(sequence >= 0), "
                "entry_sha256 TEXT NOT NULL UNIQUE, "
                "entry_json BLOB NOT NULL) STRICT"
            )
        return cls(path)

    @contextmanager
    def _transaction(self, *, write: bool) -> Generator[sqlite3.Connection, None, None]:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("routing control anchor identity or policy changed")
            yield connection

    def _entries(
        self,
        connection: sqlite3.Connection,
        activation_authorities: RoutingActivationAuthorityPolicy,
    ) -> tuple[AnchoredRoutingControl, ...]:
        if (
            activation_authorities.policy_sha256
            != self.policy.activation_authority_policy_sha256
        ):
            raise ValueError(
                "activation authority policy does not match control anchor"
            )
        rows = connection.execute(
            "SELECT sequence, entry_sha256, entry_json "
            "FROM control_entries ORDER BY sequence"
        ).fetchall()
        entries: list[AnchoredRoutingControl] = []
        previous: AnchoredRoutingControl | None = None
        for stored_sequence, stored_digest, payload in rows:
            entry = AnchoredRoutingControl.model_validate_json(payload)
            control = entry.signed_control.control
            if (
                entry.anchor_id != self.policy.anchor_id
                or stored_sequence != control.sequence
                or stored_digest != entry.anchor_entry_sha256
                or payload != canonical_bytes(entry)
                or entry.previous_entry_sha256
                != (previous.anchor_entry_sha256 if previous is not None else None)
            ):
                raise ValueError("routing control anchor chain is invalid")
            signer = verify_signed_routing_activation_control(
                entry.signed_control, activation_authorities
            )
            if signer.authority_id not in self.policy.control_authority_ids:
                raise ValueError("control signer is not authorized by anchor policy")
            if previous is not None:
                prior = previous.signed_control.control
                if (
                    control.sequence <= prior.sequence
                    or control.issued_at <= prior.issued_at
                    or entry.anchored_at < previous.anchored_at
                    or not set(prior.revoked_candidate_policy_sha256)
                    <= set(control.revoked_candidate_policy_sha256)
                    or not set(prior.revoked_promotion_receipt_sha256)
                    <= set(control.revoked_promotion_receipt_sha256)
                ):
                    raise ValueError("routing control anchor is not monotonic")
            entries.append(entry)
            previous = entry
        return tuple(entries)

    def snapshot(
        self, activation_authorities: RoutingActivationAuthorityPolicy
    ) -> RoutingControlAnchorSnapshot:
        with self._transaction(write=False) as connection:
            entries = self._entries(connection, activation_authorities)
            return RoutingControlAnchorSnapshot(
                policy=self.policy,
                entries=len(entries),
                latest=entries[-1] if entries else None,
            )

    def advance(
        self,
        signed_control: SignedRoutingActivationControl,
        activation_authorities: RoutingActivationAuthorityPolicy,
        now: datetime,
    ) -> RoutingControlAnchorSnapshot:
        _require_utc(now)
        control = signed_control.control
        if not control.issued_at <= now < control.valid_until:
            raise ValueError("only a current routing control state can be anchored")
        with self._transaction(write=True) as connection:
            entries = self._entries(connection, activation_authorities)
            previous = entries[-1] if entries else None
            if previous is not None:
                prior = previous.signed_control.control
                if control.sequence <= prior.sequence:
                    raise ValueError("routing control sequence did not advance")
                if control.issued_at <= prior.issued_at or now < previous.anchored_at:
                    raise ValueError("routing control time did not advance")
                if not set(prior.revoked_candidate_policy_sha256) <= set(
                    control.revoked_candidate_policy_sha256
                ) or not set(prior.revoked_promotion_receipt_sha256) <= set(
                    control.revoked_promotion_receipt_sha256
                ):
                    raise ValueError("routing control revocations cannot be removed")
            signer = verify_signed_routing_activation_control(
                signed_control, activation_authorities
            )
            if signer.authority_id not in self.policy.control_authority_ids:
                raise ValueError("control signer is not authorized by anchor policy")
            entry = AnchoredRoutingControl(
                anchor_id=self.policy.anchor_id,
                previous_entry_sha256=(
                    previous.anchor_entry_sha256 if previous is not None else None
                ),
                anchored_at=now,
                signed_control=signed_control,
            )
            connection.execute(
                "INSERT INTO control_entries VALUES (?, ?, ?)",
                (
                    control.sequence,
                    entry.anchor_entry_sha256,
                    canonical_bytes(entry),
                ),
            )
            updated = (*entries, entry)
            return RoutingControlAnchorSnapshot(
                policy=self.policy,
                entries=len(updated),
                latest=entry,
            )

    def require_latest(
        self,
        signed_control: SignedRoutingActivationControl,
        activation_authorities: RoutingActivationAuthorityPolicy,
        now: datetime,
    ) -> AnchoredRoutingControl:
        with self.guard_latest(signed_control, activation_authorities, now) as latest:
            return latest

    @contextmanager
    def guard_latest(
        self,
        signed_control: SignedRoutingActivationControl,
        activation_authorities: RoutingActivationAuthorityPolicy,
        now: datetime,
    ) -> Generator[AnchoredRoutingControl, None, None]:
        """Hold a read transaction so newer routing control cannot commit."""

        current = _require_utc(now)
        signed_control = SignedRoutingActivationControl.model_validate_json(
            canonical_bytes(signed_control)
        )
        with self._transaction(write=False) as connection:
            entries = self._entries(connection, activation_authorities)
            latest = entries[-1] if entries else None
            if latest is None:
                raise ValueError("routing control anchor has no state")
            if latest.signed_control != signed_control:
                raise ValueError(
                    "routing control state is not the latest anchored state"
                )
            control = signed_control.control
            if (
                not latest.anchored_at <= current
                or not control.issued_at <= current < control.valid_until
            ):
                raise ValueError("latest anchored routing control state is not current")
            yield latest
