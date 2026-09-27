"""Synthetic G6 witnessed control and three-scope admission; never a live authority."""

from __future__ import annotations

import base64
import binascii
import fcntl
import os
import sqlite3
import stat
from collections.abc import Callable, Generator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.routing_activation import (
    RoutingActivationAuthorityPolicy,
    verify_signed_routing_activation_control,
)
from mos_eisley.run.activation_control import (
    AnchoredRoutingControl,
    RoutingControlAnchorPolicy,
)
from mos_eisley.run.routing_preflight import RoutingRuntimePreflight
from mos_eisley.run.store import private_write

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]
_ENROLL_DOMAIN = b"mos-eisley/g6-synthetic-witness-enrollment/v1\0"
_BUDGET_DOMAIN = b"mos-eisley/g6-synthetic-budget-policy/v1\0"
_RECEIPT_DOMAIN = b"mos-eisley/g6-synthetic-admission-receipt/v1\0"
_CLAIM_DOMAIN = b"mos-eisley/g6-synthetic-witness-claim/v1\0"
_ATTEMPT_DOMAIN = b"mos-eisley/g6-offline-attempt/v1\0"
_COHORT_RELEASE_DOMAIN = b"mos-eisley/g6-synthetic-cohort-release/v1\0"


class _AssignmentAlreadyExists(ValueError):
    pass


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("witness time must use explicit UTC")
    return value


def _verify(key_hex: str, signature: str, domain: bytes, value: Contract) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex)).verify(
            base64.b64decode(signature, validate=True), domain + canonical_bytes(value)
        )
    except (InvalidSignature, ValueError, binascii.Error) as error:
        raise ValueError("synthetic witness signature is invalid") from error


def _sign(private_key: bytes, domain: bytes, value: Contract) -> str:
    return base64.b64encode(
        Ed25519PrivateKey.from_private_bytes(private_key).sign(
            domain + canonical_bytes(value)
        )
    ).decode("ascii")


def _public_hex(private_key: bytes) -> str:
    return (
        Ed25519PrivateKey.from_private_bytes(private_key)
        .public_key()
        .public_bytes_raw()
        .hex()
    )


def _connect(path: Path) -> sqlite3.Connection:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError("synthetic witness file must be private and regular")
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
            raise ValueError("synthetic witness requires rollback journaling")
        return connection
    except BaseException:
        connection.close()
        raise


@contextmanager
def _writer_lock(path: Path) -> Generator[None, None, None]:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError("synthetic witness writer fence is invalid")
    with path.open("rb") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class SyntheticAdmissionTrust(Contract):
    schema_version: Literal[1] = 1
    operator_id: Identifier
    operator_public_key_hex: Digest
    budget_id: Identifier
    budget_public_key_hex: Digest

    @model_validator(mode="after")
    def separate_keys(self) -> Self:
        if (
            self.operator_id == self.budget_id
            or self.operator_public_key_hex == self.budget_public_key_hex
        ):
            raise ValueError("synthetic operator and budget signers must differ")
        return self


class TaskSessionBinding(Contract):
    task_id: Identifier
    session_id: Identifier


class SyntheticCohortTrust(Contract):
    schema_version: Literal[1] = 1
    owner_signer_id: Identifier
    owner_public_key_hex: Digest
    operator_signer_id: Identifier
    operator_public_key_hex: Digest
    g6_05_go_sha256: Digest

    @model_validator(mode="after")
    def separated_signers(self) -> Self:
        if (
            self.owner_signer_id == self.operator_signer_id
            or self.owner_public_key_hex == self.operator_public_key_hex
        ):
            raise ValueError("synthetic cohort release signers must differ")
        return self


class CohortManifest(Contract):
    schema_version: Literal[1] = 1
    owner_id: Identifier
    cohort_id: Identifier
    witness_epoch_id: Digest
    witness_enrollment_sha256: Digest
    budget_policy_sha256: Digest
    candidate_policy_sha256: Digest
    promotion_receipt_sha256: Digest
    broker_build_sha256: Digest
    target_host_id: Identifier
    tasks: Annotated[
        tuple[TaskSessionBinding, ...], Field(min_length=1, max_length=256)
    ]
    stages: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=64)]
    max_assignments: Annotated[int, Field(gt=0, le=256)]
    max_concurrent: Annotated[int, Field(gt=0, le=256)]
    valid_from: datetime
    valid_until: datetime

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def canonical_scope(self) -> Self:
        ids = tuple(item.task_id for item in self.tasks)
        if (
            self.valid_until <= self.valid_from
            or ids != tuple(sorted(set(ids)))
            or self.stages != tuple(sorted(set(self.stages)))
            or self.max_assignments > len(self.tasks)
            or self.max_concurrent > self.max_assignments
        ):
            raise ValueError("synthetic cohort manifest is inconsistent")
        return self

    @property
    def manifest_sha256(self) -> str:
        return digest(canonical_bytes(self))


class CohortRelease(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    g6_05_go_sha256: Digest
    witness_epoch_id: Digest
    broker_build_sha256: Digest
    target_host_id: Identifier
    sequence: Annotated[int, Field(ge=0)]
    phase: Literal["shadow_only", "bounded_live", "closed"]
    issued_at: datetime
    valid_until: datetime

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("synthetic cohort release window is invalid")
        return self

    @property
    def release_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SignedCohortRelease(Contract):
    release: CohortRelease
    owner_signer_id: Identifier
    owner_signature_base64: str
    operator_signer_id: Identifier
    operator_signature_base64: str


def sign_synthetic_cohort_release(
    release: CohortRelease,
    *,
    owner_signer_id: str,
    owner_private_key: bytes,
    operator_signer_id: str,
    operator_private_key: bytes,
) -> SignedCohortRelease:
    return SignedCohortRelease(
        release=release,
        owner_signer_id=owner_signer_id,
        owner_signature_base64=_sign(
            owner_private_key, _COHORT_RELEASE_DOMAIN, release
        ),
        operator_signer_id=operator_signer_id,
        operator_signature_base64=_sign(
            operator_private_key, _COHORT_RELEASE_DOMAIN, release
        ),
    )


def verify_synthetic_cohort_release(
    signed: SignedCohortRelease,
    trust: SyntheticCohortTrust,
    manifest: CohortManifest,
) -> None:
    release = signed.release
    if (
        signed.owner_signer_id != trust.owner_signer_id
        or signed.operator_signer_id != trust.operator_signer_id
        or release.g6_05_go_sha256 != trust.g6_05_go_sha256
        or release.manifest_sha256 != manifest.manifest_sha256
        or release.witness_epoch_id != manifest.witness_epoch_id
        or release.broker_build_sha256 != manifest.broker_build_sha256
        or release.target_host_id != manifest.target_host_id
        or release.valid_until > manifest.valid_until
    ):
        raise ValueError("synthetic cohort release binding is invalid")
    _verify(
        trust.owner_public_key_hex,
        signed.owner_signature_base64,
        _COHORT_RELEASE_DOMAIN,
        release,
    )
    _verify(
        trust.operator_public_key_hex,
        signed.operator_signature_base64,
        _COHORT_RELEASE_DOMAIN,
        release,
    )


class CohortBudgetPolicy(Contract):
    schema_version: Literal[1] = 1
    owner_id: Identifier
    cohort_id: Identifier
    tasks: Annotated[
        tuple[TaskSessionBinding, ...], Field(min_length=1, max_length=256)
    ]
    valid_from: datetime
    valid_until: datetime
    task_ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    session_ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    cohort_ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    request_maximum_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    max_tasks: Annotated[int, Field(gt=0, le=256)]
    max_sessions: Annotated[int, Field(gt=0, le=256)]
    max_attempts: Annotated[int, Field(gt=0, le=100_000)]
    max_unresolved: Annotated[int, Field(gt=0, le=100_000)]
    execution_profile_sha256: Digest

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def canonical_scopes(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("synthetic budget policy window is invalid")
        ids = tuple(item.task_id for item in self.tasks)
        sessions = {item.session_id for item in self.tasks}
        if (
            ids != tuple(sorted(set(ids)))
            or len(ids) > self.max_tasks
            or len(sessions) > self.max_sessions
        ):
            raise ValueError("synthetic task/session enrollment is invalid")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SignedCohortBudgetPolicy(Contract):
    policy: CohortBudgetPolicy
    signer_id: Identifier
    signature_base64: str


def sign_cohort_budget_policy(
    policy: CohortBudgetPolicy, signer_id: str, private_key: bytes
) -> SignedCohortBudgetPolicy:
    return SignedCohortBudgetPolicy(
        policy=policy,
        signer_id=signer_id,
        signature_base64=_sign(private_key, _BUDGET_DOMAIN, policy),
    )


class WitnessEnrollment(Contract):
    schema_version: Literal[1] = 1
    epoch_id: Digest
    witness_id: Digest
    witness_public_key_hex: Digest
    checkpoint_id: Digest
    anchor_policy_sha256: Digest
    activation_authority_policy_sha256: Digest
    genesis_entry_sha256: Digest
    genesis_sequence: Annotated[int, Field(ge=0)]
    budget_policy_sha256: Digest
    owner_id: Identifier
    cohort_id: Identifier
    valid_from: datetime
    valid_until: datetime

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("synthetic enrollment window is invalid")
        return self

    @property
    def enrollment_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SignedWitnessEnrollment(Contract):
    enrollment: WitnessEnrollment
    signer_id: Identifier
    signature_base64: str


def sign_witness_enrollment(
    enrollment: WitnessEnrollment, signer_id: str, private_key: bytes
) -> SignedWitnessEnrollment:
    return SignedWitnessEnrollment(
        enrollment=enrollment,
        signer_id=signer_id,
        signature_base64=_sign(private_key, _ENROLL_DOMAIN, enrollment),
    )


class WitnessedAttempt(Contract):
    schema_version: Literal[1] = 1
    attempt_key: Digest
    owner_id: Identifier
    cohort_id: Identifier
    task_id: Identifier
    session_id: Identifier
    stage_id: Identifier
    attempt_id: Identifier
    envelope_sha256: Digest
    request_sha256: Digest
    selection_sha256: Digest
    profile_sha256: Digest
    candidate_id: Digest
    candidate_policy_sha256: Digest
    promotion_receipt_sha256: Digest
    preflight_sha256: Digest
    control_sequence: Annotated[int, Field(ge=0)]
    control_anchor_entry_sha256: Digest
    maximum_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    budget_policy_sha256: Digest

    @model_validator(mode="after")
    def canonical_attempt_identity(self) -> Self:
        identity = _AttemptIdentity(
            values=(
                self.owner_id,
                self.cohort_id,
                self.task_id,
                self.stage_id,
                self.attempt_id,
            )
        )
        if self.attempt_key != digest(_ATTEMPT_DOMAIN + canonical_bytes(identity)):
            raise ValueError("synthetic witnessed attempt key is not canonical")
        return self


class _AttemptIdentity(Contract):
    values: tuple[Identifier, Identifier, Identifier, Identifier, Identifier]


class Checkpoint(Contract):
    schema_version: Literal[1] = 1
    checkpoint_id: Digest
    epoch_id: Digest
    generation: Annotated[int, Field(ge=0)]
    state_sha256: Digest
    previous_sha256: Digest | None = None

    @property
    def checkpoint_sha256(self) -> str:
        return digest(canonical_bytes(self))


class WitnessedAdmissionReceipt(Contract):
    schema_version: Literal[1] = 1
    witness_id: Digest
    epoch_id: Digest
    generation: Annotated[int, Field(ge=1)]
    attempt_key: Digest
    claim_id: Digest
    owner_id: Identifier
    cohort_id: Identifier
    task_id: Identifier
    session_id: Identifier
    request_sha256: Digest
    envelope_sha256: Digest
    budget_policy_sha256: Digest
    reserved_microusd: Annotated[int, Field(gt=0)]
    control_sequence: Annotated[int, Field(ge=0)]
    control_anchor_entry_sha256: Digest
    committed_at: datetime
    valid_until: datetime
    signature_base64: str

    @field_validator("committed_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_until <= self.committed_at:
            raise ValueError("synthetic admission receipt window is invalid")
        return self


class _UnsignedReceipt(Contract):
    schema_version: Literal[1] = 1
    witness_id: Digest
    epoch_id: Digest
    generation: Annotated[int, Field(ge=1)]
    attempt_key: Digest
    claim_id: Digest
    owner_id: Identifier
    cohort_id: Identifier
    task_id: Identifier
    session_id: Identifier
    request_sha256: Digest
    envelope_sha256: Digest
    budget_policy_sha256: Digest
    reserved_microusd: Annotated[int, Field(gt=0)]
    control_sequence: Annotated[int, Field(ge=0)]
    control_anchor_entry_sha256: Digest
    committed_at: datetime
    valid_until: datetime


def verify_admission_receipt(
    receipt: WitnessedAdmissionReceipt,
    enrollment: WitnessEnrollment,
    attempt: WitnessedAttempt,
    now: datetime,
) -> None:
    _utc(now)
    unsigned = _UnsignedReceipt.model_validate(
        receipt.model_dump(exclude={"signature_base64"})
    )
    _verify(
        enrollment.witness_public_key_hex,
        receipt.signature_base64,
        _RECEIPT_DOMAIN,
        unsigned,
    )
    if (
        receipt.witness_id != enrollment.witness_id
        or receipt.epoch_id != enrollment.epoch_id
        or receipt.attempt_key != attempt.attempt_key
        or receipt.owner_id != attempt.owner_id
        or receipt.cohort_id != attempt.cohort_id
        or receipt.task_id != attempt.task_id
        or receipt.session_id != attempt.session_id
        or receipt.request_sha256 != attempt.request_sha256
        or receipt.envelope_sha256 != attempt.envelope_sha256
        or receipt.budget_policy_sha256 != attempt.budget_policy_sha256
        or receipt.reserved_microusd != attempt.maximum_microusd
        or receipt.control_sequence != attempt.control_sequence
        or receipt.control_anchor_entry_sha256 != attempt.control_anchor_entry_sha256
        or not receipt.committed_at <= now < receipt.valid_until
    ):
        raise ValueError("synthetic admission receipt provenance or time mismatch")


class WitnessedAttemptRecord(Contract):
    attempt: WitnessedAttempt
    claim_id: Digest
    admitted_generation: Annotated[int, Field(ge=1)]
    status: Literal["held", "settled", "uncertain", "violation"]
    charged_microusd: Money


class WitnessedAssignment(Contract):
    owner_id: Identifier
    cohort_id: Identifier
    task_id: Identifier
    session_id: Identifier
    stage_id: Identifier
    candidate_policy_sha256: Digest
    release_sha256: Digest
    assigned_generation: Annotated[int, Field(ge=1)]
    assigned_at: datetime

    @field_validator("assigned_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class WitnessedCohortState(Contract):
    trust: SyntheticCohortTrust
    manifest: CohortManifest
    signed_release: SignedCohortRelease
    assignments: tuple[WitnessedAssignment, ...]

    @model_validator(mode="after")
    def authenticated_release(self) -> Self:
        verify_synthetic_cohort_release(self.signed_release, self.trust, self.manifest)
        ids = tuple(item.task_id for item in self.assignments)
        if ids != tuple(sorted(set(ids))) or len(ids) > self.manifest.max_assignments:
            raise ValueError("synthetic cohort assignment roster is invalid")
        if any(
            item.owner_id != self.manifest.owner_id
            or item.cohort_id != self.manifest.cohort_id
            or item.candidate_policy_sha256 != self.manifest.candidate_policy_sha256
            or TaskSessionBinding(task_id=item.task_id, session_id=item.session_id)
            not in self.manifest.tasks
            or item.stage_id not in self.manifest.stages
            for item in self.assignments
        ):
            raise ValueError("synthetic cohort assignment provenance is invalid")
        return self


class WitnessedState(Contract):
    epoch_id: Digest
    generation: Annotated[int, Field(ge=0)]
    control: AnchoredRoutingControl
    attempts: tuple[WitnessedAttemptRecord, ...]
    cohort: WitnessedCohortState | None = None

    @property
    def state_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ScopeSnapshot(Contract):
    task_charged_microusd: Money
    session_charged_microusd: Money
    cohort_charged_microusd: Money
    unresolved_entries: Annotated[int, Field(ge=0)]
    blocked: bool


class SyntheticCheckpointStore:
    """Separate local fixture standing in for independently retained high water."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT checkpoint_json FROM checkpoint"
            ).fetchall()
            if len(rows) != 1:
                raise ValueError("synthetic checkpoint is missing")
            self.identity = Checkpoint.model_validate_json(rows[0][0]).checkpoint_id

    @classmethod
    def create(cls, path: Path, initial: Checkpoint) -> Self:
        private_write(path, b"")
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE checkpoint (singleton INTEGER PRIMARY KEY "
                "CHECK(singleton=1), "
                "checkpoint_json BLOB NOT NULL) STRICT"
            )
            connection.execute(
                "INSERT INTO checkpoint VALUES (1, ?)", (canonical_bytes(initial),)
            )
        return cls(path)

    def read_current(self) -> Checkpoint:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                "SELECT checkpoint_json FROM checkpoint"
            ).fetchall()
            if len(rows) != 1:
                raise ValueError("synthetic checkpoint is invalid")
            current = Checkpoint.model_validate_json(rows[0][0])
            if current.checkpoint_id != self.identity or rows[0][0] != canonical_bytes(
                current
            ):
                raise ValueError("synthetic checkpoint identity or encoding changed")
            return current

    def compare_and_swap(self, previous: Checkpoint, successor: Checkpoint) -> None:
        if (
            previous.checkpoint_id != self.identity
            or successor.checkpoint_id != self.identity
            or successor.epoch_id != previous.epoch_id
            or successor.generation != previous.generation + 1
            or successor.previous_sha256 != previous.checkpoint_sha256
        ):
            raise ValueError("synthetic checkpoint successor is invalid")
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT checkpoint_json FROM checkpoint"
            ).fetchall()
            if len(rows) != 1 or rows[0][0] != canonical_bytes(previous):
                raise ValueError("synthetic checkpoint compare-and-swap failed")
            connection.execute(
                "UPDATE checkpoint SET checkpoint_json=? WHERE singleton=1",
                (canonical_bytes(successor),),
            )


class SyntheticWitnessedAdmission:
    """One synthetic, checkpointed control/claim/budget writer."""

    def __init__(
        self,
        path: Path,
        checkpoint: SyntheticCheckpointStore,
        trust: SyntheticAdmissionTrust,
        anchor_policy: RoutingControlAnchorPolicy,
        activation_authorities: RoutingActivationAuthorityPolicy,
        witness_private_key: bytes,
    ):
        self.path = path.absolute()
        self.lock_path = self.path.with_suffix(".lock")
        self.checkpoint = checkpoint
        self.trust = trust
        self.anchor_policy = anchor_policy
        self.activation_authorities = activation_authorities
        self.witness_private_key = witness_private_key
        with closing(_connect(self.path)) as connection:
            enrollment, budget = self._config(connection)
        self.enrollment = enrollment
        self.budget_policy = budget
        if _public_hex(witness_private_key) != enrollment.witness_public_key_hex:
            raise ValueError("synthetic witness signing key does not match enrollment")
        if checkpoint.identity != enrollment.checkpoint_id:
            raise ValueError("synthetic checkpoint identity mismatch")
        self.read_current()

    @classmethod
    def bootstrap(
        cls,
        *,
        path: Path,
        checkpoint_path: Path,
        signed_enrollment: SignedWitnessEnrollment,
        signed_budget: SignedCohortBudgetPolicy,
        trust: SyntheticAdmissionTrust,
        genesis: AnchoredRoutingControl,
        anchor_policy: RoutingControlAnchorPolicy,
        activation_authorities: RoutingActivationAuthorityPolicy,
        witness_private_key: bytes,
        now: datetime,
    ) -> Self:
        _utc(now)
        enrollment = signed_enrollment.enrollment
        budget = signed_budget.policy
        cls._verify_config(
            signed_enrollment,
            signed_budget,
            trust,
            anchor_policy,
            activation_authorities,
        )
        cls._verify_control(genesis, anchor_policy, activation_authorities)
        if (
            genesis.previous_entry_sha256 is not None
            or genesis.anchor_entry_sha256 != enrollment.genesis_entry_sha256
            or genesis.signed_control.control.sequence != enrollment.genesis_sequence
            or _public_hex(witness_private_key) != enrollment.witness_public_key_hex
            or not enrollment.valid_from <= now < enrollment.valid_until
            or not budget.valid_from <= now < budget.valid_until
            or not genesis.signed_control.control.issued_at
            <= now
            < genesis.signed_control.control.valid_until
            or genesis.anchored_at > now
        ):
            raise ValueError("synthetic witness genesis is not independently enrolled")
        state = WitnessedState(
            epoch_id=enrollment.epoch_id,
            generation=0,
            control=genesis,
            attempts=(),
        )
        first_checkpoint = Checkpoint(
            checkpoint_id=enrollment.checkpoint_id,
            epoch_id=enrollment.epoch_id,
            generation=0,
            state_sha256=state.state_sha256,
        )
        private_write(path.with_suffix(".lock"), b"")
        private_write(path, b"")
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE config (singleton INTEGER PRIMARY KEY "
                "CHECK(singleton=1), "
                "enrollment_json BLOB NOT NULL, budget_json BLOB NOT NULL) STRICT"
            )
            connection.execute(
                "INSERT INTO config VALUES (1, ?, ?)",
                (canonical_bytes(signed_enrollment), canonical_bytes(signed_budget)),
            )
            connection.execute(
                "CREATE TABLE meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                "generation INTEGER NOT NULL, state_sha256 TEXT NOT NULL) STRICT"
            )
            connection.execute(
                "INSERT INTO meta VALUES (1, 0, ?)", (state.state_sha256,)
            )
            connection.execute(
                "CREATE TABLE control (singleton INTEGER PRIMARY KEY "
                "CHECK(singleton=1), "
                "entry_json BLOB NOT NULL) STRICT"
            )
            connection.execute(
                "INSERT INTO control VALUES (1, ?)", (canonical_bytes(genesis),)
            )
            connection.execute(
                "CREATE TABLE attempts (attempt_key TEXT PRIMARY KEY, "
                "claim_id TEXT NOT NULL UNIQUE, record_json BLOB NOT NULL) STRICT"
            )
            connection.execute(
                "CREATE TABLE cohort (singleton INTEGER PRIMARY KEY "
                "CHECK(singleton=1), cohort_json BLOB NOT NULL) STRICT"
            )
            connection.execute(
                "CREATE TABLE assignments (task_id TEXT PRIMARY KEY, "
                "record_json BLOB NOT NULL) STRICT"
            )
        checkpoint = SyntheticCheckpointStore.create(checkpoint_path, first_checkpoint)
        return cls(
            path,
            checkpoint,
            trust,
            anchor_policy,
            activation_authorities,
            witness_private_key,
        )

    @staticmethod
    def _verify_config(
        signed_enrollment: SignedWitnessEnrollment,
        signed_budget: SignedCohortBudgetPolicy,
        trust: SyntheticAdmissionTrust,
        anchor_policy: RoutingControlAnchorPolicy,
        activation_authorities: RoutingActivationAuthorityPolicy,
    ) -> None:
        enrollment = signed_enrollment.enrollment
        budget = signed_budget.policy
        if (
            signed_enrollment.signer_id != trust.operator_id
            or signed_budget.signer_id != trust.budget_id
            or enrollment.anchor_policy_sha256 != anchor_policy.policy_sha256
            or enrollment.activation_authority_policy_sha256
            != activation_authorities.policy_sha256
            or anchor_policy.activation_authority_policy_sha256
            != activation_authorities.policy_sha256
            or enrollment.budget_policy_sha256 != budget.policy_sha256
            or enrollment.owner_id != budget.owner_id
            or enrollment.cohort_id != budget.cohort_id
        ):
            raise ValueError("synthetic witness enrollment or scope policy mismatch")
        _verify(
            trust.operator_public_key_hex,
            signed_enrollment.signature_base64,
            _ENROLL_DOMAIN,
            enrollment,
        )
        _verify(
            trust.budget_public_key_hex,
            signed_budget.signature_base64,
            _BUDGET_DOMAIN,
            budget,
        )

    @staticmethod
    def _verify_control(
        entry: AnchoredRoutingControl,
        anchor_policy: RoutingControlAnchorPolicy,
        activation_authorities: RoutingActivationAuthorityPolicy,
    ) -> None:
        signer = verify_signed_routing_activation_control(
            entry.signed_control, activation_authorities
        )
        if (
            entry.anchor_id != anchor_policy.anchor_id
            or signer.authority_id not in anchor_policy.control_authority_ids
        ):
            raise ValueError("synthetic witness control signer or anchor is invalid")

    def _config(
        self, connection: sqlite3.Connection
    ) -> tuple[WitnessEnrollment, CohortBudgetPolicy]:
        rows = connection.execute(
            "SELECT enrollment_json, budget_json FROM config"
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("synthetic witness configuration is missing")
        signed_enrollment = SignedWitnessEnrollment.model_validate_json(rows[0][0])
        signed_budget = SignedCohortBudgetPolicy.model_validate_json(rows[0][1])
        if rows[0][0] != canonical_bytes(signed_enrollment) or rows[0][
            1
        ] != canonical_bytes(signed_budget):
            raise ValueError("synthetic witness configuration is noncanonical")
        self._verify_config(
            signed_enrollment,
            signed_budget,
            self.trust,
            self.anchor_policy,
            self.activation_authorities,
        )
        return signed_enrollment.enrollment, signed_budget.policy

    def _state(
        self, connection: sqlite3.Connection, *, verify: bool = True
    ) -> WitnessedState:
        enrollment, budget = self._config(connection)
        if hasattr(self, "enrollment") and (
            enrollment != self.enrollment or budget != self.budget_policy
        ):
            raise ValueError("synthetic witness enrollment changed")
        meta = connection.execute(
            "SELECT generation, state_sha256 FROM meta"
        ).fetchall()
        control_rows = connection.execute("SELECT entry_json FROM control").fetchall()
        if len(meta) != 1 or len(control_rows) != 1:
            raise ValueError("synthetic witness state is incomplete")
        control = AnchoredRoutingControl.model_validate_json(control_rows[0][0])
        self._verify_control(control, self.anchor_policy, self.activation_authorities)
        if control_rows[0][0] != canonical_bytes(control):
            raise ValueError("synthetic witness control is noncanonical")
        rows = connection.execute(
            "SELECT attempt_key, claim_id, record_json FROM attempts "
            "ORDER BY attempt_key"
        ).fetchall()
        attempts: list[WitnessedAttemptRecord] = []
        for attempt_key, claim_id, raw in rows:
            record = WitnessedAttemptRecord.model_validate_json(raw)
            if (
                raw != canonical_bytes(record)
                or record.attempt.attempt_key != attempt_key
                or record.claim_id != claim_id
            ):
                raise ValueError("synthetic witness attempt row is invalid")
            attempts.append(record)
        cohort_rows = connection.execute("SELECT cohort_json FROM cohort").fetchall()
        assignment_rows = connection.execute(
            "SELECT task_id, record_json FROM assignments ORDER BY task_id"
        ).fetchall()
        if len(cohort_rows) > 1 or (not cohort_rows and assignment_rows):
            raise ValueError("synthetic cohort journal is invalid")
        cohort: WitnessedCohortState | None = None
        if cohort_rows:
            stored = WitnessedCohortState.model_validate_json(cohort_rows[0][0])
            assignments: list[WitnessedAssignment] = []
            for task_id, raw in assignment_rows:
                assignment = WitnessedAssignment.model_validate_json(raw)
                if raw != canonical_bytes(assignment) or assignment.task_id != task_id:
                    raise ValueError("synthetic cohort assignment row is invalid")
                assignments.append(assignment)
            cohort = WitnessedCohortState(
                trust=stored.trust,
                manifest=stored.manifest,
                signed_release=stored.signed_release,
                assignments=tuple(assignments),
            )
            if cohort_rows[0][0] != canonical_bytes(
                stored.model_copy(update={"assignments": ()})
            ):
                raise ValueError("synthetic cohort journal is noncanonical")
        state = WitnessedState(
            epoch_id=enrollment.epoch_id,
            generation=meta[0][0],
            control=control,
            attempts=tuple(attempts),
            cohort=cohort,
        )
        if verify and state.state_sha256 != meta[0][1]:
            raise ValueError("synthetic witness state digest disagrees with journal")
        return state

    def _checkpoint_matches(self, state: WitnessedState) -> Checkpoint:
        checkpoint = self.checkpoint.read_current()
        if (
            checkpoint.checkpoint_id != self.enrollment.checkpoint_id
            or checkpoint.epoch_id != self.enrollment.epoch_id
            or checkpoint.generation != state.generation
            or checkpoint.state_sha256 != state.state_sha256
        ):
            raise ValueError("synthetic witness journal/checkpoint mismatch")
        return checkpoint

    def read_current(self) -> WitnessedState:
        with (
            _writer_lock(self.lock_path),
            closing(_connect(self.path)) as connection,
            connection,
        ):
            connection.execute("BEGIN")
            state = self._state(connection)
            self._checkpoint_matches(state)
            return state

    def _commit[T](
        self,
        mutation: Callable[[sqlite3.Connection, WitnessedState], T],
        fault: Callable[[str], None] | None = None,
    ) -> tuple[T, WitnessedState]:
        with _writer_lock(self.lock_path):
            with closing(_connect(self.path)) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                state = self._state(connection)
                previous = self._checkpoint_matches(state)
                if fault is not None:
                    fault("before_db_commit")
                result = mutation(connection, state)
                connection.execute(
                    "UPDATE meta SET generation=? WHERE singleton=1",
                    (state.generation + 1,),
                )
                updated = self._state(connection, verify=False)
                connection.execute(
                    "UPDATE meta SET state_sha256=? WHERE singleton=1",
                    (updated.state_sha256,),
                )
            if fault is not None:
                fault("after_db_commit")
            successor = Checkpoint(
                checkpoint_id=previous.checkpoint_id,
                epoch_id=previous.epoch_id,
                generation=updated.generation,
                state_sha256=updated.state_sha256,
                previous_sha256=previous.checkpoint_sha256,
            )
            self.checkpoint.compare_and_swap(previous, successor)
            if fault is not None:
                fault("after_checkpoint")
            return result, updated

    def enroll_cohort(
        self,
        *,
        manifest: CohortManifest,
        trust: SyntheticCohortTrust,
        signed_release: SignedCohortRelease,
        now: datetime,
        fault: Callable[[str], None] | None = None,
    ) -> WitnessedCohortState:
        """Enroll one synthetic shadow lineage in the existing checkpointed journal."""
        _utc(now)
        verify_synthetic_cohort_release(signed_release, trust, manifest)
        if (
            manifest.owner_id != self.enrollment.owner_id
            or manifest.cohort_id != self.enrollment.cohort_id
            or manifest.witness_epoch_id != self.enrollment.epoch_id
            or manifest.witness_enrollment_sha256 != self.enrollment.enrollment_sha256
            or manifest.budget_policy_sha256 != self.budget_policy.policy_sha256
            or any(item not in self.budget_policy.tasks for item in manifest.tasks)
            or manifest.max_assignments > self.budget_policy.max_tasks
            or signed_release.release.sequence != 0
            or signed_release.release.phase != "shadow_only"
            or not manifest.valid_from <= now < manifest.valid_until
            or not signed_release.release.issued_at
            <= now
            < signed_release.release.valid_until
        ):
            raise ValueError("synthetic cohort enrollment is invalid")

        def enroll(connection: sqlite3.Connection, state: WitnessedState) -> None:
            if (
                state.cohort is not None
                or state.attempts
                or state.control.signed_control.control.emergency_stop
            ):
                raise ValueError("synthetic cohort cannot be re-enrolled")
            entry = WitnessedCohortState(
                trust=trust,
                manifest=manifest,
                signed_release=signed_release,
                assignments=(),
            )
            connection.execute(
                "INSERT INTO cohort VALUES (1, ?)", (canonical_bytes(entry),)
            )

        _, updated = self._commit(enroll, fault)
        assert updated.cohort is not None
        return updated.cohort

    def advance_cohort_release(
        self,
        *,
        signed_release: SignedCohortRelease,
        now: datetime,
        fault: Callable[[str], None] | None = None,
    ) -> WitnessedCohortState:
        _utc(now)

        def advance(connection: sqlite3.Connection, state: WitnessedState) -> None:
            cohort = state.cohort
            if cohort is None:
                raise ValueError("synthetic cohort is not enrolled")
            verify_synthetic_cohort_release(
                signed_release, cohort.trust, cohort.manifest
            )
            prior = cohort.signed_release.release
            current = signed_release.release
            if (
                prior.phase == "closed"
                or current.sequence != prior.sequence + 1
                or current.issued_at <= prior.issued_at
                or current.issued_at > now
                or not now < current.valid_until
                or not cohort.manifest.valid_from <= now < cohort.manifest.valid_until
                or (prior.phase == "bounded_live" and current.phase == "shadow_only")
                or (
                    current.phase == "bounded_live"
                    and state.control.signed_control.control.emergency_stop
                )
            ):
                raise ValueError("synthetic cohort release did not advance safely")
            changed = cohort.model_copy(
                update={"signed_release": signed_release, "assignments": ()}
            )
            connection.execute(
                "UPDATE cohort SET cohort_json=? WHERE singleton=1",
                (canonical_bytes(changed),),
            )

        _, updated = self._commit(advance, fault)
        assert updated.cohort is not None
        return updated.cohort

    def assign_cohort_task(
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
        _utc(now)

        def existing(state: WitnessedState) -> WitnessedAssignment | None:
            cohort = state.cohort
            if cohort is None:
                return None
            found = next(
                (item for item in cohort.assignments if item.task_id == task_id),
                None,
            )
            if found is None:
                return None
            if (
                found.owner_id != owner_id
                or found.cohort_id != cohort_id
                or found.session_id != session_id
                or found.stage_id != stage_id
                or found.candidate_policy_sha256 != candidate_policy_sha256
                or found.release_sha256 != expected_release_sha256
            ):
                raise ValueError("synthetic cohort duplicate assignment conflicts")
            return found

        prior = existing(self.read_current())
        if prior is not None:
            return prior

        def assign(
            connection: sqlite3.Connection, state: WitnessedState
        ) -> WitnessedAssignment:
            cohort = state.cohort
            control = state.control.signed_control.control
            if cohort is None:
                raise ValueError("synthetic cohort is not enrolled")
            if any(item.task_id == task_id for item in cohort.assignments):
                raise _AssignmentAlreadyExists("synthetic assignment raced")
            release = cohort.signed_release.release
            manifest = cohort.manifest
            if (
                release.phase != "bounded_live"
                or release.release_sha256 != expected_release_sha256
                or not release.issued_at <= now < release.valid_until
                or not manifest.valid_from <= now < manifest.valid_until
                or not control.issued_at <= now < control.valid_until
                or control.emergency_stop
                or candidate_policy_sha256 in control.revoked_candidate_policy_sha256
                or owner_id != manifest.owner_id
                or cohort_id != manifest.cohort_id
                or candidate_policy_sha256 != manifest.candidate_policy_sha256
                or TaskSessionBinding(task_id=task_id, session_id=session_id)
                not in manifest.tasks
                or stage_id not in manifest.stages
                or len(cohort.assignments) >= manifest.max_assignments
            ):
                raise ValueError("synthetic cohort assignment is ineligible")
            record = WitnessedAssignment(
                owner_id=owner_id,
                cohort_id=cohort_id,
                task_id=task_id,
                session_id=session_id,
                stage_id=stage_id,
                candidate_policy_sha256=candidate_policy_sha256,
                release_sha256=expected_release_sha256,
                assigned_generation=state.generation + 1,
                assigned_at=now,
            )
            connection.execute(
                "INSERT INTO assignments VALUES (?, ?)",
                (task_id, canonical_bytes(record)),
            )
            return record

        try:
            record, _ = self._commit(assign, fault)
        except _AssignmentAlreadyExists:
            raced = existing(self.read_current())
            if raced is None:
                raise
            return raced
        return record

    def inspect_cohort(
        self, *, owner_id: str, cohort_id: str
    ) -> WitnessedCohortState | None:
        if (
            owner_id != self.enrollment.owner_id
            or cohort_id != self.enrollment.cohort_id
        ):
            raise ValueError("synthetic cohort inspection scope denied")
        return self.read_current().cohort

    def claim_with_budget(
        self,
        *,
        attempt: WitnessedAttempt,
        expected_control: AnchoredRoutingControl,
        current_preflight: RoutingRuntimePreflight,
        now: datetime,
        fault: Callable[[str], None] | None = None,
    ) -> WitnessedAdmissionReceipt:
        _utc(now)
        current_preflight.check_current(now)
        if (
            attempt.owner_id != self.budget_policy.owner_id
            or attempt.cohort_id != self.budget_policy.cohort_id
            or attempt.budget_policy_sha256 != self.budget_policy.policy_sha256
            or attempt.profile_sha256 != self.budget_policy.execution_profile_sha256
            or attempt.maximum_microusd != self.budget_policy.request_maximum_microusd
            or attempt.candidate_policy_sha256
            != current_preflight.candidate_policy_sha256
            or attempt.promotion_receipt_sha256
            != current_preflight.promotion_receipt_sha256
            or attempt.preflight_sha256 != current_preflight.preflight_sha256
            or attempt.candidate_id not in current_preflight.eligible_candidate_ids
            or attempt.control_anchor_entry_sha256
            != current_preflight.anchored_control_entry_sha256
            or current_preflight.control_anchor_policy_sha256
            != self.enrollment.anchor_policy_sha256
            or not self.enrollment.valid_from <= now < self.enrollment.valid_until
            or not self.budget_policy.valid_from <= now < self.budget_policy.valid_until
            or TaskSessionBinding(
                task_id=attempt.task_id, session_id=attempt.session_id
            )
            not in self.budget_policy.tasks
        ):
            raise ValueError("synthetic witnessed admission provenance is invalid")
        claim_id = digest(
            _CLAIM_DOMAIN
            + bytes.fromhex(self.enrollment.epoch_id)
            + bytes.fromhex(attempt.attempt_key)
            + bytes.fromhex(attempt.request_sha256)
        )

        def admit(
            connection: sqlite3.Connection, state: WitnessedState
        ) -> WitnessedAttemptRecord:
            control = state.control.signed_control.control
            cohort = state.cohort
            if cohort is not None:
                release = cohort.signed_release.release
                manifest = cohort.manifest
                assignment = next(
                    (
                        item
                        for item in cohort.assignments
                        if item.task_id == attempt.task_id
                    ),
                    None,
                )
                if (
                    release.phase != "bounded_live"
                    or not release.issued_at <= now < release.valid_until
                    or not manifest.valid_from <= now < manifest.valid_until
                    or attempt.candidate_policy_sha256
                    != manifest.candidate_policy_sha256
                    or attempt.promotion_receipt_sha256
                    != manifest.promotion_receipt_sha256
                    or attempt.owner_id != manifest.owner_id
                    or attempt.cohort_id != manifest.cohort_id
                    or attempt.stage_id not in manifest.stages
                    or assignment is None
                    or assignment.session_id != attempt.session_id
                    or assignment.stage_id != attempt.stage_id
                    or assignment.release_sha256 != release.release_sha256
                    or any(
                        row.attempt.task_id == attempt.task_id for row in state.attempts
                    )
                    or sum(row.status != "settled" for row in state.attempts)
                    >= manifest.max_concurrent
                ):
                    raise ValueError("synthetic cohort claim has no active slot")
            if (
                state.control != expected_control
                or attempt.control_sequence != control.sequence
                or attempt.control_anchor_entry_sha256
                != state.control.anchor_entry_sha256
                or not control.issued_at <= now < control.valid_until
                or control.emergency_stop
                or attempt.candidate_policy_sha256
                in control.revoked_candidate_policy_sha256
                or attempt.promotion_receipt_sha256
                in control.revoked_promotion_receipt_sha256
                or any(
                    row.attempt.attempt_key == attempt.attempt_key
                    for row in state.attempts
                )
                or len(state.attempts) >= self.budget_policy.max_attempts
                or sum(row.status != "settled" for row in state.attempts)
                >= self.budget_policy.max_unresolved
                or any(row.status == "violation" for row in state.attempts)
            ):
                raise ValueError("synthetic witnessed control or attempt is ineligible")
            totals = self._totals(state, attempt.task_id, attempt.session_id)
            for total, ceiling in (
                (
                    totals.task_charged_microusd,
                    self.budget_policy.task_ceiling_microusd,
                ),
                (
                    totals.session_charged_microusd,
                    self.budget_policy.session_ceiling_microusd,
                ),
                (
                    totals.cohort_charged_microusd,
                    self.budget_policy.cohort_ceiling_microusd,
                ),
            ):
                if total + attempt.maximum_microusd > ceiling:
                    raise ValueError("synthetic witnessed budget scope exhausted")
            record = WitnessedAttemptRecord(
                attempt=attempt,
                claim_id=claim_id,
                admitted_generation=state.generation + 1,
                status="held",
                charged_microusd=attempt.maximum_microusd,
            )
            connection.execute(
                "INSERT INTO attempts VALUES (?, ?, ?)",
                (attempt.attempt_key, claim_id, canonical_bytes(record)),
            )
            return record

        record, updated = self._commit(admit, fault)
        valid_until = min(
            now + timedelta(seconds=30),
            self.enrollment.valid_until,
            self.budget_policy.valid_until,
            expected_control.signed_control.control.valid_until,
            current_preflight.valid_until,
        )
        if updated.cohort is not None:
            valid_until = min(
                valid_until,
                updated.cohort.manifest.valid_until,
                updated.cohort.signed_release.release.valid_until,
            )
        unsigned = _UnsignedReceipt(
            witness_id=self.enrollment.witness_id,
            epoch_id=self.enrollment.epoch_id,
            generation=updated.generation,
            attempt_key=attempt.attempt_key,
            claim_id=record.claim_id,
            owner_id=attempt.owner_id,
            cohort_id=attempt.cohort_id,
            task_id=attempt.task_id,
            session_id=attempt.session_id,
            request_sha256=attempt.request_sha256,
            envelope_sha256=attempt.envelope_sha256,
            budget_policy_sha256=attempt.budget_policy_sha256,
            reserved_microusd=attempt.maximum_microusd,
            control_sequence=attempt.control_sequence,
            control_anchor_entry_sha256=attempt.control_anchor_entry_sha256,
            committed_at=now,
            valid_until=valid_until,
        )
        if fault is not None:
            fault("before_receipt")
        return WitnessedAdmissionReceipt(
            **unsigned.model_dump(),
            signature_base64=_sign(self.witness_private_key, _RECEIPT_DOMAIN, unsigned),
        )

    def advance_control(
        self,
        entry: AnchoredRoutingControl,
        now: datetime,
        fault: Callable[[str], None] | None = None,
    ) -> WitnessedState:
        _utc(now)
        self._verify_control(entry, self.anchor_policy, self.activation_authorities)

        def advance(connection: sqlite3.Connection, state: WitnessedState) -> None:
            prior = state.control.signed_control.control
            next_control = entry.signed_control.control
            if (
                entry.previous_entry_sha256 != state.control.anchor_entry_sha256
                or entry.anchor_id != state.control.anchor_id
                or next_control.sequence <= prior.sequence
                or next_control.issued_at <= prior.issued_at
                or entry.anchored_at < state.control.anchored_at
                or entry.anchored_at > now
                or not next_control.issued_at <= now < next_control.valid_until
                or not set(prior.revoked_candidate_policy_sha256)
                <= set(next_control.revoked_candidate_policy_sha256)
                or not set(prior.revoked_promotion_receipt_sha256)
                <= set(next_control.revoked_promotion_receipt_sha256)
                or (prior.emergency_stop and not next_control.emergency_stop)
            ):
                raise ValueError("synthetic witnessed control did not advance safely")
            connection.execute(
                "UPDATE control SET entry_json=? WHERE singleton=1",
                (canonical_bytes(entry),),
            )

        _, updated = self._commit(advance, fault)
        return updated

    def settle_exact(
        self,
        *,
        receipt: WitnessedAdmissionReceipt,
        charged_microusd: int,
        status: Literal["settled", "uncertain", "violation"],
        now: datetime,
        fault: Callable[[str], None] | None = None,
    ) -> WitnessedAttemptRecord:
        _utc(now)
        if charged_microusd < 0:
            raise ValueError("synthetic settlement cannot be negative")

        def settle(
            connection: sqlite3.Connection, state: WitnessedState
        ) -> WitnessedAttemptRecord:
            matches = [
                item
                for item in state.attempts
                if item.attempt.attempt_key == receipt.attempt_key
            ]
            if len(matches) != 1:
                raise ValueError("synthetic witnessed settlement has no claim")
            current = matches[0]
            verify_admission_receipt(
                receipt,
                self.enrollment,
                current.attempt,
                receipt.committed_at,
            )
            if (
                current.claim_id != receipt.claim_id
                or current.admitted_generation != receipt.generation
                or current.status != "held"
                or charged_microusd > current.attempt.maximum_microusd
                or (
                    status != "settled"
                    and charged_microusd != current.attempt.maximum_microusd
                )
            ):
                raise ValueError("synthetic witnessed settlement is not exact")
            updated = current.model_copy(
                update={"status": status, "charged_microusd": charged_microusd}
            )
            connection.execute(
                "UPDATE attempts SET record_json=? WHERE attempt_key=?",
                (canonical_bytes(updated), receipt.attempt_key),
            )
            return updated

        record, _ = self._commit(settle, fault)
        return record

    @staticmethod
    def _totals(state: WitnessedState, task_id: str, session_id: str) -> ScopeSnapshot:
        return ScopeSnapshot(
            task_charged_microusd=sum(
                row.charged_microusd
                for row in state.attempts
                if row.attempt.task_id == task_id
            ),
            session_charged_microusd=sum(
                row.charged_microusd
                for row in state.attempts
                if row.attempt.session_id == session_id
            ),
            cohort_charged_microusd=sum(row.charged_microusd for row in state.attempts),
            unresolved_entries=sum(row.status != "settled" for row in state.attempts),
            blocked=any(row.status == "violation" for row in state.attempts),
        )

    def inspect_attempt(
        self, *, owner_id: str, cohort_id: str, attempt_key: str
    ) -> WitnessedAttemptRecord | None:
        if (
            owner_id != self.budget_policy.owner_id
            or cohort_id != self.budget_policy.cohort_id
        ):
            raise ValueError("synthetic witnessed inspection scope denied")
        state = self.read_current()
        return next(
            (row for row in state.attempts if row.attempt.attempt_key == attempt_key),
            None,
        )

    def inspect_scopes(
        self, *, owner_id: str, cohort_id: str, task_id: str, session_id: str
    ) -> ScopeSnapshot:
        if (
            owner_id != self.budget_policy.owner_id
            or cohort_id != self.budget_policy.cohort_id
            or TaskSessionBinding(task_id=task_id, session_id=session_id)
            not in self.budget_policy.tasks
        ):
            raise ValueError("synthetic witnessed scope inspection denied")
        return self._totals(self.read_current(), task_id, session_id)
