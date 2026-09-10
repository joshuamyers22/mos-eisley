"""Independent authorization and atomic selection of one inert installed skill."""

from __future__ import annotations

import base64
import binascii
import os
import sqlite3
import stat
from collections.abc import Generator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.skills import SkillIdentity, SkillPackageArchive
from mos_eisley.evaluation.models import EvaluationDataset, SweepPlan
from mos_eisley.evaluation.skill_comparison import (
    SealedSkillComparison,
    SkillComparisonReport,
    SkillHoldoutUseClaim,
)
from mos_eisley.evaluation.skill_promotion import (
    AuthenticatedSkillPromotion,
    SkillEvaluationLineage,
    SkillPromotionAuthorityPolicy,
)
from mos_eisley.run.skill_installation import SkillInstallationAuthorityPolicy
from mos_eisley.run.skill_installed_store import (
    InstalledSkillManifest,
    SkillInstalledStore,
)
from mos_eisley.run.skill_release import SkillReleaseEvidence
from mos_eisley.run.skill_release_control import (
    AuthenticatedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillReleaseControlAuthorityPolicy,
    authenticate_skill_release_control,
    verify_authenticated_skill_release_control,
)
from mos_eisley.run.store import private_write

_DOMAIN = b"mos-eisley/skill-default-selection/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class TrustedSkillDefaultAuthority(Contract):
    authority_id: Identifier
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: EncodedKey

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode(self.public_key_base64, 32, "public key")
        return self

    @property
    def public_key_sha256(self) -> str:
        return digest(_decode(self.public_key_base64, 32, "public key"))


class SkillDefaultAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_default_authority_policy"] = "skill_default_authority_policy"
    policy_id: Identifier
    installed_store_policy_sha256: Digest
    installation_authority_policy_sha256: Digest
    control_anchor_policy_sha256: Digest
    default_store_id: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_decision_lifetime_seconds: Annotated[int, Field(gt=0, le=86_400)]
    authorities: Annotated[
        tuple[TrustedSkillDefaultAuthority, ...], Field(min_length=1, max_length=20)
    ]
    may_authorize_default_pointer_change: Literal[True] = True
    other_configuration_mutation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("skill default authority window must be positive")
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "skill default authorities need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillDefaultDecision(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_default_decision"] = "skill_default_decision"
    authority_policy_sha256: Digest
    installed_store_policy_sha256: Digest
    installation_authority_policy_sha256: Digest
    installed_manifest_sha256: Digest
    installation_authorization_sha256: Digest
    installation_decision_sha256: Digest
    control_anchor_policy_sha256: Digest
    control_anchor_entry_sha256: Digest
    signed_control_sha256: Digest
    release_evidence_sha256: Digest
    default_store_id: Digest
    sequence: Annotated[int, Field(ge=1, le=9_223_372_036_854_775_807)]
    expected_previous_pointer_sha256: Digest | None
    action: Literal["candidate", "rollback"]
    archive_sha256: Digest
    skill: SkillIdentity
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    one_use_required: Literal[True] = True
    default_pointer_mutation_authorized: Literal[True] = True
    other_configuration_mutation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("skill default decision window must be positive")
        if self.skill.kind != "persona":
            raise ValueError("a default can select only a persona skill")
        if (self.sequence == 1) != (self.expected_previous_pointer_sha256 is None):
            raise ValueError("skill default sequence and previous pointer disagree")
        return self

    @property
    def decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillDefaultSignature(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    signer_id: Identifier
    public_key_sha256: Digest
    decision_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedSkillDefaultDecision(Contract):
    schema_version: Literal[1] = 1
    decision: SkillDefaultDecision
    signature: SkillDefaultSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.decision_sha256 != self.decision.decision_sha256:
            raise ValueError("signature does not identify this skill default decision")
        return self

    @property
    def signed_decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedSkillDefault(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["authenticated_skill_default"] = "authenticated_skill_default"
    authority_policy_sha256: Digest
    installed_manifest_sha256: Digest
    archive_sha256: Digest
    skill: SkillIdentity
    default_store_id: Digest
    signed_decision: SignedSkillDefaultDecision
    authenticated_at: UtcTimestamp
    valid_until: UtcTimestamp
    one_use_required: Literal[True] = True
    default_pointer_mutation_authorized: Literal[True] = True
    default_changed: Literal[False] = False
    other_configuration_mutation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False

    @field_validator("authenticated_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_sources(self) -> Self:
        decision = self.signed_decision.decision
        if (
            self.authority_policy_sha256 != decision.authority_policy_sha256
            or self.installed_manifest_sha256 != decision.installed_manifest_sha256
            or self.archive_sha256 != decision.archive_sha256
            or self.skill != decision.skill
            or self.default_store_id != decision.default_store_id
            or self.valid_until != decision.valid_until
            or not decision.issued_at <= self.authenticated_at < self.valid_until
        ):
            raise ValueError("authenticated skill default source mismatch")
        return self

    @property
    def authorization_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def check_current(self, now: datetime) -> None:
        current = _require_utc(now)
        if not self.authenticated_at <= current < self.valid_until:
            raise ValueError("skill default authorization is not current")


class SkillDefaultStorePolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_default_store_policy"] = "skill_default_store_policy"
    store_id: Digest
    authority_policy_sha256: Digest
    installed_store_policy_sha256: Digest
    max_revisions: Annotated[int, Field(ge=1, le=100_000)] = 10_000
    max_history_bytes: Annotated[int, Field(ge=1_000_000, le=256_000_000)] = 64_000_000
    may_mutate_default_pointer: Literal[True] = True
    runtime_lookup_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    other_configuration_mutation_authorized: Literal[False] = False

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillDefaultPointer(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["selected_skill_default_pointer"] = "selected_skill_default_pointer"
    default_store_policy_sha256: Digest
    sequence: Annotated[int, Field(ge=1, le=9_223_372_036_854_775_807)]
    previous_pointer_sha256: Digest | None
    decision_sha256: Digest
    authorization_sha256: Digest
    installed_manifest_sha256: Digest
    archive_sha256: Digest
    skill: SkillIdentity
    selected_at: UtcTimestamp
    authorization_consumed: Literal[True] = True
    default_changed: Literal[True] = True
    other_configuration_mutation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False

    @field_validator("selected_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def chain_shape(self) -> Self:
        if (self.sequence == 1) != (self.previous_pointer_sha256 is None):
            raise ValueError("skill default pointer chain shape is invalid")
        return self

    @property
    def pointer_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillDefaultSelectionRecord(Contract):
    schema_version: Literal[1] = 1
    pointer: SkillDefaultPointer
    authorization: AuthenticatedSkillDefault

    @model_validator(mode="after")
    def bound_authorization(self) -> Self:
        decision = self.authorization.signed_decision.decision
        if (
            self.pointer.decision_sha256 != decision.decision_sha256
            or self.pointer.authorization_sha256
            != self.authorization.authorization_sha256
            or self.pointer.installed_manifest_sha256
            != self.authorization.installed_manifest_sha256
            or self.pointer.archive_sha256 != self.authorization.archive_sha256
            or self.pointer.skill != self.authorization.skill
            or self.pointer.sequence != decision.sequence
            or self.pointer.previous_pointer_sha256
            != decision.expected_previous_pointer_sha256
            or not self.authorization.authenticated_at
            <= self.pointer.selected_at
            < decision.valid_until
        ):
            raise ValueError("skill default record does not match its authorization")
        return self


class SkillDefaultStoreSnapshot(Contract):
    schema_version: Literal[1] = 1
    policy: SkillDefaultStorePolicy
    revisions: Annotated[int, Field(ge=0, le=100_000)]
    current: SkillDefaultPointer | None
    atomic_commit: Literal[True] = True
    automatic_recovery_required: Literal[False] = False
    default_changed: Literal[False] = False
    other_configuration_mutation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def consistent_count(self) -> Self:
        if (self.revisions == 0) != (self.current is None):
            raise ValueError("skill default revision count and pointer disagree")
        if self.current is not None and self.current.sequence != self.revisions:
            raise ValueError("skill default current pointer is not the latest revision")
        return self

    @property
    def snapshot_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillDefaultSelectionResult(Contract):
    schema_version: Literal[1] = 1
    pointer: SkillDefaultPointer
    authorization: AuthenticatedSkillDefault
    default_changed: Literal[True] = True
    authorization_consumed: Literal[True] = True
    atomic_commit: Literal[True] = True
    other_configuration_mutation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    runtime_lookup_authorized: Literal[False] = False


def trusted_skill_default_authority(
    authority_id: str, public_key: bytes
) -> TrustedSkillDefaultAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedSkillDefaultAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def sign_skill_default_decision(
    decision: SkillDefaultDecision,
    signer_id: str,
    private_key: bytes,
) -> SignedSkillDefaultDecision:
    decision = SkillDefaultDecision.model_validate_json(canonical_bytes(decision))
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(_DOMAIN + canonical_bytes(decision))
        public_key = key.public_key().public_bytes_raw()
    except (TypeError, ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return SignedSkillDefaultDecision(
        decision=decision,
        signature=SkillDefaultSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            decision_sha256=decision.decision_sha256,
            signature_base64=base64.b64encode(signature).decode("ascii"),
        ),
    )


def verify_signed_skill_default_decision(
    signed: SignedSkillDefaultDecision,
    policy: SkillDefaultAuthorityPolicy,
) -> TrustedSkillDefaultAuthority:
    signed = SignedSkillDefaultDecision.model_validate_json(canonical_bytes(signed))
    policy = SkillDefaultAuthorityPolicy.model_validate_json(canonical_bytes(policy))
    decision = signed.decision
    if (
        decision.authority_policy_sha256 != policy.policy_sha256
        or decision.installed_store_policy_sha256
        != policy.installed_store_policy_sha256
        or decision.installation_authority_policy_sha256
        != policy.installation_authority_policy_sha256
        or decision.control_anchor_policy_sha256 != policy.control_anchor_policy_sha256
        or decision.default_store_id != policy.default_store_id
        or not policy.valid_from
        <= decision.issued_at
        < decision.valid_until
        <= policy.valid_until
    ):
        raise ValueError("skill default decision does not match authority policy")
    if (
        decision.valid_until - decision.issued_at
    ).total_seconds() > policy.max_decision_lifetime_seconds:
        raise ValueError("skill default decision exceeds its maximum lifetime")
    matches = [
        item
        for item in policy.authorities
        if item.authority_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("signer is not trusted by the skill default policy")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("signature key differs from skill default policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(decision),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError("skill default signature verification failed") from None
    return trusted


def _validate_private_database(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ValueError("skill default store must be a regular file")
    if metadata.st_uid != os.getuid() or metadata.st_nlink != 1:
        raise ValueError("skill default store ownership is invalid")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError("skill default store must have mode 0600")


def _validate_private_directory(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ValueError("skill default store parent must be a directory")
    if metadata.st_uid != os.getuid():
        raise ValueError("skill default store parent ownership is invalid")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("skill default store parent must be private")


def _connect(path: Path) -> sqlite3.Connection:
    _validate_private_directory(path.absolute().parent)
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
            raise ValueError("skill default store requires rollback journaling")
        return connection
    except BaseException:
        connection.close()
        raise


def _load_policy(connection: sqlite3.Connection) -> SkillDefaultStorePolicy:
    rows = connection.execute(
        "SELECT value FROM metadata WHERE key = 'policy'"
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("skill default store policy is missing")
    payload = bytes(rows[0][0])
    policy = SkillDefaultStorePolicy.model_validate_json(payload)
    if payload != canonical_bytes(policy):
        raise ValueError("skill default store policy is not canonical")
    return policy


class SkillDefaultStore:
    """Atomic one-use selection history; no runtime code reads this store."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _load_policy(connection)

    @classmethod
    def create(
        cls,
        path: Path,
        policy: SkillDefaultStorePolicy,
        authority_policy: SkillDefaultAuthorityPolicy,
        installed_store: SkillInstalledStore,
    ) -> SkillDefaultStore:
        policy = SkillDefaultStorePolicy.model_validate_json(canonical_bytes(policy))
        authority_policy = SkillDefaultAuthorityPolicy.model_validate_json(
            canonical_bytes(authority_policy)
        )
        if (
            policy.store_id != authority_policy.default_store_id
            or policy.authority_policy_sha256 != authority_policy.policy_sha256
            or policy.installed_store_policy_sha256
            != installed_store.policy.policy_sha256
            or authority_policy.installed_store_policy_sha256
            != installed_store.policy.policy_sha256
            or authority_policy.installation_authority_policy_sha256
            != installed_store.policy.installation_authority_policy_sha256
        ):
            raise ValueError(
                "skill default store policy does not match trusted sources"
            )
        _validate_private_directory(path.absolute().parent)
        private_write(path, b"")
        try:
            with closing(_connect(path)) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "CREATE TABLE metadata ("
                    "key TEXT PRIMARY KEY, value BLOB NOT NULL) STRICT"
                )
                connection.execute(
                    "CREATE TABLE selections ("
                    "sequence INTEGER PRIMARY KEY CHECK(sequence >= 1), "
                    "pointer_sha256 TEXT NOT NULL UNIQUE, "
                    "decision_sha256 TEXT NOT NULL UNIQUE, "
                    "record BLOB NOT NULL) STRICT"
                )
                connection.execute(
                    "CREATE TABLE current_pointer ("
                    "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
                    "sequence INTEGER NOT NULL, pointer_sha256 TEXT NOT NULL) STRICT"
                )
                connection.execute(
                    "INSERT INTO metadata(key, value) VALUES ('policy', ?)",
                    (canonical_bytes(policy),),
                )
            directory_fd = os.open(
                path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return cls(path)

    def _records(
        self,
        connection: sqlite3.Connection,
        authority_policy: SkillDefaultAuthorityPolicy,
        installed_store: SkillInstalledStore,
        installation_policy: SkillInstallationAuthorityPolicy,
    ) -> tuple[SkillDefaultSelectionRecord, ...]:
        if (
            self.policy.store_id != authority_policy.default_store_id
            or self.policy.authority_policy_sha256 != authority_policy.policy_sha256
            or self.policy.installed_store_policy_sha256
            != installed_store.policy.policy_sha256
            or authority_policy.installation_authority_policy_sha256
            != installation_policy.policy_sha256
        ):
            raise ValueError("skill default store does not match trusted policies")
        bounds = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(record)), 0), "
            "COALESCE(MAX(LENGTH(record)), 0) FROM selections"
        ).fetchone()
        if (
            bounds is None
            or int(bounds[0]) > self.policy.max_revisions
            or int(bounds[1]) > self.policy.max_history_bytes
            or int(bounds[2]) > 512_000
        ):
            raise ValueError("skill default selection history exceeds policy")
        rows = connection.execute(
            "SELECT sequence, pointer_sha256, decision_sha256, record "
            "FROM selections ORDER BY sequence"
        ).fetchall()
        records: list[SkillDefaultSelectionRecord] = []
        previous: SkillDefaultPointer | None = None
        installed_cache: dict[
            str, tuple[InstalledSkillManifest, SkillPackageArchive, str, str]
        ] = {}
        for stored_sequence, stored_pointer, stored_decision, payload in rows:
            record = SkillDefaultSelectionRecord.model_validate_json(bytes(payload))
            pointer = record.pointer
            decision = record.authorization.signed_decision.decision
            verify_signed_skill_default_decision(
                record.authorization.signed_decision, authority_policy
            )
            installed = installed_cache.get(pointer.archive_sha256)
            if installed is None:
                installed_manifest, archive, installation_authorization, _ = (
                    installed_store.load(pointer.archive_sha256, installation_policy)
                )
                installed = (
                    installed_manifest,
                    archive,
                    installation_authorization.authorization_sha256,
                    installation_authorization.signed_decision.decision.decision_sha256,
                )
                installed_cache[pointer.archive_sha256] = installed
            (
                installed_manifest,
                archive,
                installation_authorization_sha256,
                installation_decision_sha256,
            ) = installed
            if (
                bytes(payload) != canonical_bytes(record)
                or stored_sequence != pointer.sequence
                or stored_pointer != pointer.pointer_sha256
                or stored_decision != pointer.decision_sha256
                or pointer.default_store_policy_sha256 != self.policy.policy_sha256
                or pointer.previous_pointer_sha256
                != (previous.pointer_sha256 if previous is not None else None)
                or pointer.installed_manifest_sha256
                != installed_manifest.manifest_sha256
                or pointer.archive_sha256 != archive.archive_sha256
                or pointer.skill != archive.descriptor.identity
                or decision.installed_store_policy_sha256
                != installed_store.policy.policy_sha256
                or decision.installation_authority_policy_sha256
                != installation_policy.policy_sha256
                or decision.installed_manifest_sha256
                != installed_manifest.manifest_sha256
                or decision.installation_authorization_sha256
                != installation_authorization_sha256
                or decision.installation_decision_sha256 != installation_decision_sha256
                or decision.action != installed_manifest.intent.action
                or decision.skill != archive.descriptor.identity
                or decision.default_store_id != self.policy.store_id
            ):
                raise ValueError("skill default selection history is invalid")
            records.append(record)
            previous = pointer
        current_rows = connection.execute(
            "SELECT sequence, pointer_sha256 FROM current_pointer WHERE singleton = 1"
        ).fetchall()
        if not records:
            if current_rows:
                raise ValueError("empty skill default history has a current pointer")
        elif len(current_rows) != 1 or current_rows[0] != (
            records[-1].pointer.sequence,
            records[-1].pointer.pointer_sha256,
        ):
            raise ValueError("skill default current pointer is not latest")
        return tuple(records)

    def snapshot(
        self,
        authority_policy: SkillDefaultAuthorityPolicy,
        installed_store: SkillInstalledStore,
        installation_policy: SkillInstallationAuthorityPolicy,
    ) -> SkillDefaultStoreSnapshot:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("skill default store identity or policy changed")
            records = self._records(
                connection, authority_policy, installed_store, installation_policy
            )
        return SkillDefaultStoreSnapshot(
            policy=self.policy,
            revisions=len(records),
            current=records[-1].pointer if records else None,
        )

    @contextmanager
    def guard_current(
        self,
        authority_policy: SkillDefaultAuthorityPolicy,
        installed_store: SkillInstalledStore,
        installation_policy: SkillInstallationAuthorityPolicy,
    ) -> Generator[SkillDefaultPointer, None, None]:
        """Hold a verified current-pointer read lock across a caller commit."""
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("skill default store identity or policy changed")
            records = self._records(
                connection, authority_policy, installed_store, installation_policy
            )
            if not records:
                raise ValueError("skill default store has no current pointer")
            yield records[-1].pointer

    def _select_under_guard(
        self,
        authorization: AuthenticatedSkillDefault,
        installed_manifest: InstalledSkillManifest,
        authority_policy: SkillDefaultAuthorityPolicy,
        installed_store: SkillInstalledStore,
        installation_policy: SkillInstallationAuthorityPolicy,
        now: datetime,
    ) -> SkillDefaultSelectionResult:
        current = _require_utc(now)
        authorization.check_current(current)
        verify_signed_skill_default_decision(
            authorization.signed_decision, authority_policy
        )
        decision = authorization.signed_decision.decision
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if _load_policy(connection) != self.policy:
                raise ValueError("skill default store identity or policy changed")
            records = self._records(
                connection, authority_policy, installed_store, installation_policy
            )
            previous = records[-1].pointer if records else None
            if len(records) >= self.policy.max_revisions:
                raise ValueError("skill default revision limit reached")
            if (
                decision.default_store_id != self.policy.store_id
                or decision.sequence != len(records) + 1
                or decision.expected_previous_pointer_sha256
                != (previous.pointer_sha256 if previous is not None else None)
                or decision.installed_manifest_sha256
                != installed_manifest.manifest_sha256
                or authorization.installed_manifest_sha256
                != installed_manifest.manifest_sha256
                or (
                    previous is not None
                    and previous.archive_sha256 == authorization.archive_sha256
                )
            ):
                raise ValueError("skill default authorization is stale or mismatched")
            pointer = SkillDefaultPointer(
                default_store_policy_sha256=self.policy.policy_sha256,
                sequence=decision.sequence,
                previous_pointer_sha256=decision.expected_previous_pointer_sha256,
                decision_sha256=decision.decision_sha256,
                authorization_sha256=authorization.authorization_sha256,
                installed_manifest_sha256=installed_manifest.manifest_sha256,
                archive_sha256=authorization.archive_sha256,
                skill=authorization.skill,
                selected_at=current,
            )
            record = SkillDefaultSelectionRecord(
                pointer=pointer, authorization=authorization
            )
            try:
                connection.execute(
                    "INSERT INTO selections VALUES (?, ?, ?, ?)",
                    (
                        pointer.sequence,
                        pointer.pointer_sha256,
                        pointer.decision_sha256,
                        canonical_bytes(record),
                    ),
                )
            except sqlite3.IntegrityError:
                raise ValueError(
                    "skill default authorization was already consumed"
                ) from None
            connection.execute(
                "INSERT INTO current_pointer VALUES (1, ?, ?) "
                "ON CONFLICT(singleton) DO UPDATE SET "
                "sequence = excluded.sequence, "
                "pointer_sha256 = excluded.pointer_sha256",
                (pointer.sequence, pointer.pointer_sha256),
            )
        return SkillDefaultSelectionResult(pointer=pointer, authorization=authorization)


def _validate_authority_separation(
    default_policy: SkillDefaultAuthorityPolicy,
    installation_policy: SkillInstallationAuthorityPolicy,
    control_policy: SkillReleaseControlAuthorityPolicy,
    promotion_policy: SkillPromotionAuthorityPolicy,
    lineages: tuple[SkillEvaluationLineage, SkillEvaluationLineage],
) -> None:
    upstream = (
        *installation_policy.authorities,
        *control_policy.authorities,
        *promotion_policy.authorities,
    )
    excluded_ids = {item.authority_id for item in upstream}
    excluded_keys = {item.public_key_sha256 for item in upstream}
    excluded_ids |= {
        item.adjudicator_id for lineage in lineages for item in lineage[5].adjudicators
    } | {item.adjudicator_id for lineage in lineages for item in lineage[6].resolvers}
    excluded_keys |= {
        item.public_key_sha256
        for lineage in lineages
        for item in lineage[5].adjudicators
    } | {
        item.public_key_sha256 for lineage in lineages for item in lineage[6].resolvers
    }
    if any(
        item.authority_id in excluded_ids or item.public_key_sha256 in excluded_keys
        for item in default_policy.authorities
    ):
        raise ValueError(
            "skill default authority must be independent of installation, release "
            "control, promotion, and evaluation"
        )


def _verified_installed_selection(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    installed_store: SkillInstalledStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    default_policy: SkillDefaultAuthorityPolicy,
    action: Literal["candidate", "rollback"],
    now: datetime,
) -> tuple[
    InstalledSkillManifest, SkillPackageArchive, AuthenticatedSkillReleaseControl
]:
    current = _require_utc(now)
    verify_authenticated_skill_release_control(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
    )
    current_control = authenticate_skill_release_control(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control.signed_control,
        control_policy,
        control.rollback_archive,
        current,
    )
    _validate_authority_separation(
        default_policy,
        installation_policy,
        control_policy,
        promotion_policy,
        (calibration, holdout),
    )
    if (
        default_policy.installed_store_policy_sha256
        != installed_store.policy.policy_sha256
        or default_policy.installation_authority_policy_sha256
        != installation_policy.policy_sha256
        or default_policy.control_anchor_policy_sha256 != anchor.policy.policy_sha256
        or installed_store.policy.installation_authority_policy_sha256
        != installation_policy.policy_sha256
    ):
        raise ValueError(
            "skill default policy does not match installed or control state"
        )
    selected = archive if action == "candidate" else current_control.rollback_archive
    if action == "candidate" and not current_control.release_allowed:
        raise ValueError("candidate default requires an allowed release")
    if action == "rollback" and not current_control.release_revoked:
        raise ValueError("rollback default requires a revoked release")
    if selected is None:
        raise ValueError("skill default control has no rollback archive")
    installed_manifest, installed_archive, installation_authorization, _ = (
        installed_store.load(selected.archive_sha256, installation_policy)
    )
    if (
        installed_archive != selected
        or installed_manifest.intent.action != action
        or installed_manifest.intent.archive_sha256 != selected.archive_sha256
        or installation_authorization.archive_sha256 != selected.archive_sha256
    ):
        raise ValueError("installed skill package does not match current selection")
    return installed_manifest, installed_archive, current_control


def make_skill_default_decision(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    installed_store: SkillInstalledStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    default_store: SkillDefaultStore,
    default_policy: SkillDefaultAuthorityPolicy,
    action: Literal["candidate", "rollback"],
    issued_at: datetime,
    valid_until: datetime,
) -> SkillDefaultDecision:
    """Derive one exact state-bound default pointer mutation for signing."""
    issued = _require_utc(issued_at)
    expires = _require_utc(valid_until)
    installed_manifest, selected, current_control = _verified_installed_selection(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        installed_store,
        installation_policy,
        default_policy,
        action,
        issued,
    )
    if (
        default_store.policy.store_id != default_policy.default_store_id
        or default_store.policy.authority_policy_sha256 != default_policy.policy_sha256
        or default_store.policy.installed_store_policy_sha256
        != installed_store.policy.policy_sha256
    ):
        raise ValueError("skill default store does not match authority policy")
    if not (
        default_policy.valid_from <= issued < expires <= default_policy.valid_until
        and expires <= current_control.valid_until
        and expires <= evidence.valid_until
    ):
        raise ValueError("skill default window exceeds a source validity window")
    if (
        expires - issued
    ).total_seconds() > default_policy.max_decision_lifetime_seconds:
        raise ValueError("skill default decision exceeds its maximum lifetime")
    snapshot = default_store.snapshot(
        default_policy, installed_store, installation_policy
    )
    if (
        snapshot.current is not None
        and snapshot.current.archive_sha256 == selected.archive_sha256
    ):
        raise ValueError("selected skill package is already the default")
    _, _, installation_authorization, _ = installed_store.load(
        selected.archive_sha256, installation_policy
    )
    with anchor.guard_latest(current_control, control_policy, issued) as anchored:
        return SkillDefaultDecision(
            authority_policy_sha256=default_policy.policy_sha256,
            installed_store_policy_sha256=installed_store.policy.policy_sha256,
            installation_authority_policy_sha256=installation_policy.policy_sha256,
            installed_manifest_sha256=installed_manifest.manifest_sha256,
            installation_authorization_sha256=(
                installation_authorization.authorization_sha256
            ),
            installation_decision_sha256=(
                installation_authorization.signed_decision.decision.decision_sha256
            ),
            control_anchor_policy_sha256=anchor.policy.policy_sha256,
            control_anchor_entry_sha256=anchored.anchor_entry_sha256,
            signed_control_sha256=current_control.signed_control.signed_control_sha256,
            release_evidence_sha256=evidence.release_evidence_sha256,
            default_store_id=default_store.policy.store_id,
            sequence=snapshot.revisions + 1,
            expected_previous_pointer_sha256=(
                snapshot.current.pointer_sha256
                if snapshot.current is not None
                else None
            ),
            action=action,
            archive_sha256=selected.archive_sha256,
            skill=selected.descriptor.identity,
            issued_at=issued,
            valid_until=expires,
        )


def authenticate_skill_default(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    installed_store: SkillInstalledStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    default_store: SkillDefaultStore,
    signed: SignedSkillDefaultDecision,
    default_policy: SkillDefaultAuthorityPolicy,
    action: Literal["candidate", "rollback"],
    now: datetime,
) -> AuthenticatedSkillDefault:
    current = _require_utc(now)
    verify_signed_skill_default_decision(signed, default_policy)
    expected = make_skill_default_decision(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        installed_store,
        installation_policy,
        default_store,
        default_policy,
        action,
        signed.decision.issued_at,
        signed.decision.valid_until,
    )
    if expected != signed.decision:
        raise ValueError("signed skill default decision differs from sources")
    installed_manifest, selected, current_control = _verified_installed_selection(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        installed_store,
        installation_policy,
        default_policy,
        action,
        current,
    )
    with anchor.guard_latest(current_control, control_policy, current) as anchored:
        if (
            anchored.anchor_entry_sha256 != signed.decision.control_anchor_entry_sha256
            or installed_manifest.manifest_sha256
            != signed.decision.installed_manifest_sha256
            or selected.archive_sha256 != signed.decision.archive_sha256
        ):
            raise ValueError("skill default decision is no longer current")
    if not signed.decision.issued_at <= current < signed.decision.valid_until:
        raise ValueError("skill default decision is not current")
    return AuthenticatedSkillDefault(
        authority_policy_sha256=default_policy.policy_sha256,
        installed_manifest_sha256=installed_manifest.manifest_sha256,
        archive_sha256=selected.archive_sha256,
        skill=selected.descriptor.identity,
        default_store_id=default_store.policy.store_id,
        signed_decision=signed,
        authenticated_at=current,
        valid_until=signed.decision.valid_until,
    )


def verify_authenticated_skill_default(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    installed_store: SkillInstalledStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    default_store: SkillDefaultStore,
    authenticated: AuthenticatedSkillDefault,
    default_policy: SkillDefaultAuthorityPolicy,
    action: Literal["candidate", "rollback"],
    now: datetime,
) -> None:
    rebuilt = authenticate_skill_default(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        installed_store,
        installation_policy,
        default_store,
        authenticated.signed_decision,
        default_policy,
        action,
        authenticated.authenticated_at,
    )
    if rebuilt != authenticated:
        raise ValueError("authenticated skill default provenance mismatch")
    authenticated.check_current(now)


def select_authenticated_skill_default(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    installed_store: SkillInstalledStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    default_store: SkillDefaultStore,
    authorization: AuthenticatedSkillDefault,
    default_policy: SkillDefaultAuthorityPolicy,
    action: Literal["candidate", "rollback"],
    now: datetime,
) -> SkillDefaultSelectionResult:
    """Atomically consume exact authority and change only the inert default pointer."""
    current = _require_utc(now)
    verify_authenticated_skill_default(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        installed_store,
        installation_policy,
        default_store,
        authorization,
        default_policy,
        action,
        current,
    )
    installed_manifest, _, current_control = _verified_installed_selection(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        installed_store,
        installation_policy,
        default_policy,
        action,
        current,
    )
    with anchor.guard_latest(current_control, control_policy, current) as anchored:
        if (
            anchored.anchor_entry_sha256
            != authorization.signed_decision.decision.control_anchor_entry_sha256
        ):
            raise ValueError("skill default authorization is no longer latest")
        return default_store._select_under_guard(  # pyright: ignore[reportPrivateUsage]
            authorization,
            installed_manifest,
            default_policy,
            installed_store,
            installation_policy,
            current,
        )
